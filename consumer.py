"""
Notification Service — RabbitMQ consumer.

Listens for portfolio events and dispatches them to Celery tasks for processing.
Runs as a standalone process (separate Docker container).
"""
import os
import sys
import json
import time
import logging
import pika

# Setup logging
from shared.logging_config import setup_logging
setup_logging()

logger = logging.getLogger(__name__)

EXCHANGE_NAME = 'portfolio.events'
QUEUE_NAME = 'notification.events'
DLQ_EXCHANGE = 'portfolio.events.dlx'
DLQ_QUEUE = 'notification.events.dlq'
ROUTING_KEYS = ['portfolio.transaction.*']  # Listen to all transaction events


def get_connection_params():
    """Build RabbitMQ connection parameters from environment."""
    return pika.ConnectionParameters(
        host=os.environ.get('RABBITMQ_HOST', 'localhost'),
        port=int(os.environ.get('RABBITMQ_PORT', 5672)),
        virtual_host=os.environ.get('RABBITMQ_VHOST', '/'),
        credentials=pika.PlainCredentials(
            os.environ.get('RABBITMQ_USER', 'guest'),
            os.environ.get('RABBITMQ_PASSWORD', 'guest'),
        ),
        heartbeat=600,
        blocked_connection_timeout=300,
        connection_attempts=5,
        retry_delay=10,
    )


def setup_queues(channel):
    """Declare exchanges, queues, and bindings including Dead Letter Queue."""
    # Dead Letter Exchange & Queue
    channel.exchange_declare(exchange=DLQ_EXCHANGE, exchange_type='fanout', durable=True)
    channel.queue_declare(queue=DLQ_QUEUE, durable=True)
    channel.queue_bind(queue=DLQ_QUEUE, exchange=DLQ_EXCHANGE)

    # Main exchange
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)

    # Main queue with DLQ configuration
    channel.queue_declare(
        queue=QUEUE_NAME,
        durable=True,
        arguments={
            'x-dead-letter-exchange': DLQ_EXCHANGE,
            'x-message-ttl': 86400000,  # 24h
        },
    )

    # Bind queue to exchange with routing keys
    for key in ROUTING_KEYS:
        channel.queue_bind(queue=QUEUE_NAME, exchange=EXCHANGE_NAME, routing_key=key)

    logger.info(f"Queues setup: {QUEUE_NAME} bound to {EXCHANGE_NAME} with keys {ROUTING_KEYS}")


def on_message(channel, method, properties, body):
    """Callback for incoming messages — dispatches to Celery task."""
    try:
        event_data = json.loads(body)
        event_id = properties.message_id or properties.headers.get('event_id', 'unknown')
        event_type = (properties.headers or {}).get('event_type', 'unknown')

        logger.info(f"Received event: {event_type} [{event_id}] — routing_key={method.routing_key}")

        # Dispatch to Celery for async processing
        from tasks import process_event
        process_event.delay(event_id, event_type, event_data)

        # Acknowledge the message
        channel.basic_ack(delivery_tag=method.delivery_tag)
        logger.info(f"Event dispatched to Celery: {event_id}")

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in message: {e}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def start_consumer():
    """Start the RabbitMQ consumer with automatic reconnection."""
    while True:
        try:
            logger.info("Connecting to RabbitMQ...")
            connection = pika.BlockingConnection(get_connection_params())
            channel = connection.channel()

            setup_queues(channel)

            # Fair dispatch — don't give more than 1 message at a time
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)

            logger.info(f"✅ Consumer started — listening on queue '{QUEUE_NAME}'")
            channel.start_consuming()

        except pika.exceptions.ConnectionClosedByBroker:
            logger.warning("Connection closed by broker, reconnecting...")
            time.sleep(5)
            continue

        except pika.exceptions.AMQPChannelError as e:
            logger.error(f"Channel error: {e}, stopping.")
            break

        except pika.exceptions.AMQPConnectionError:
            logger.warning("Connection lost, reconnecting in 10s...")
            time.sleep(10)
            continue

        except KeyboardInterrupt:
            logger.info("Consumer stopped by user")
            break

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            time.sleep(10)
            continue


if __name__ == '__main__':
    start_consumer()
