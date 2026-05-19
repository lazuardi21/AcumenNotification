# Notification Service

Event-driven microservice for the **Portfolio Activity & Notification System**. Consumes portfolio events from RabbitMQ, evaluates notification rules, and delivers notifications via configurable channels (email, SMS, push).

---

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────┐
│    RabbitMQ      │────▶│     Notification Consumer            │
│  (Event Broker)  │     │     (consumer.py — separate process) │
└─────────────────┘     └──────────────┬───────────────────────┘
                                       │ dispatches
                        ┌──────────────▼───────────────────────┐
                        │         Celery Workers                │
                        │  • process_event (rule evaluation)    │
                        │  • send_notification_task (delivery)  │
                        │  • retry_failed_task (periodic)       │
                        │  • send_pending_task (periodic)       │
                        └──────────────┬───────────────────────┘
                                       │
┌──────────────┐        ┌──────────────▼───────────────────────┐
│  API Gateway │───────▶│      Notification Service (Flask)     │
│   (:5000)    │        │           (Port 5002)                 │
└──────────────┘        │                                       │
                        │  • Notification CRUD (list, mark read)│
                        │  • User Preferences (channels, quiet) │
                        │  • Rules Engine (threshold, txn, etc) │
                        └──────────────┬───────────────────────┘
                                       │
                        ┌──────────────▼───────────────────────┐
                        │           PostgreSQL                  │
                        │       (acumen_notification)           │
                        └──────────────────────────────────────┘
```

## Features

- **Notification Management** — List, mark as read, mark all as read
- **User Preferences** — Configure notification channels (email, SMS, push), quiet hours
- **Rules Engine** — Flexible rule system supporting:
  - `threshold` — Triggers when a field exceeds a value (e.g., total_amount > $5,000)
  - `transaction` — Triggers on specific transaction types (e.g., BUY, SELL)
  - `daily_summary` — Periodic summary notifications
- **RabbitMQ Consumer** — Dedicated process consuming events from `portfolio_events` exchange
- **Celery Workers** — Async task processing with 4 concurrent workers
- **Celery Beat** — Periodic tasks (retry failed every 5 min, send pending every 10 sec)
- **Idempotent Processing** — `ProcessedEvent` table prevents duplicate event handling
- **Dead Letter Queue** — Unprocessable messages are routed to DLQ for investigation
- **Mock Delivery** — Simulated email, SMS, and push notification delivery (production-ready interface)
- **Retry Mechanism** — Max 3 retries with exponential backoff for failed deliveries
- **Distributed Tracing** — OpenTelemetry + Jaeger integration
- **Structured Logging** — JSON-formatted logs with trace ID correlation

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Event Consumption** | Dedicated consumer process | Decouples event handling from HTTP request path |
| **Task Processing** | Celery + RabbitMQ | Built-in retry, rate limiting, monitoring, and concurrency |
| **Rule Engine** | Custom Python evaluator | Flexible, extensible — no external rule engine dependency |
| **Idempotency** | ProcessedEvent table | Prevents duplicate notifications from redelivered messages |
| **Notification Delivery** | Mock channels with real interface | Easy to swap in real providers (SendGrid, Twilio, Firebase) |

## Tradeoffs Considered

1. **Celery vs custom Pika consumers** — Celery adds overhead (~50MB per worker) but provides retry, rate limiting, monitoring, and periodic tasks out of the box. Custom consumers would be lighter but require reimplementing these features.

2. **Separate consumer process vs Celery-native consumption** — A dedicated `consumer.py` process gives control over message acknowledgment and error handling. Celery's built-in AMQP consumer is more opinionated but less flexible for custom routing.

3. **Rule engine in code vs external (Drools, OPA)** — A Python-based rules engine is simpler and sufficient for this scope. An external engine would add complexity but enable non-developer rule management.

4. **Eager notification delivery vs batched** — Immediate delivery provides real-time responsiveness. Batching would reduce system load but adds latency. The `send_pending_task` periodic job handles any notifications that weren't delivered immediately.

5. **Shared Flask app instance for Celery** — Using a cached `_app_instance` avoids recreating the Flask app on every forked Celery process. This is pragmatic but requires care with thread safety.

## Scalability Considerations

- **Celery concurrency**: Configurable worker concurrency (default: 4). Scale horizontally by adding more worker containers.
- **Consumer parallelism**: Multiple consumer processes can connect to the same RabbitMQ queue for parallel event processing.
- **Database**: Connection pooling via SQLAlchemy. Read replicas can be added for notification list queries.
- **Rate limiting**: Celery task rate limiting prevents overwhelming external notification providers.
- **Queue durability**: RabbitMQ queues and exchanges are durable — messages survive broker restarts.

## Project Structure

```
notification_service/
├── app.py              # Flask application factory
├── config.py           # Configuration (dev/prod/testing)
├── models.py           # SQLAlchemy models (Notification, Preference, Rule, ProcessedEvent)
├── routes.py           # REST API endpoints (notifications, preferences, rules)
├── services.py         # Business logic layer
├── rule_engine.py      # Rule evaluation engine
├── celery_app.py       # Celery configuration and initialization
├── tasks.py            # Celery task definitions
├── consumer.py         # RabbitMQ event consumer (standalone process)
├── seed.py             # Demo data seeder
├── wsgi.py             # Gunicorn WSGI entry point
├── Dockerfile          # Container build
├── Jenkinsfile         # CI/CD pipeline
├── requirements.txt    # Python dependencies
└── shared/             # Shared utilities
    ├── auth.py         # JWT encode/decode helpers
    ├── tracing.py      # OpenTelemetry setup
    └── logging_config.py  # Structured logging
```

## Data Models

```
Notification
├── id (PK)
├── user_id
├── type (transaction_alert, threshold_alert, daily_summary)
├── title
├── message
├── data (JSON — event payload)
├── channel (email, sms, push)
├── status (pending, sent, failed, read)
├── read (boolean)
├── retry_count
├── rule_name
└── created_at / sent_at

NotificationPreference
├── id (PK)
├── user_id (unique)
├── email_enabled (default: true)
├── sms_enabled (default: false)
├── push_enabled (default: true)
├── quiet_hours_start / end
└── created_at / updated_at

NotificationRule
├── id (PK)
├── user_id
├── name
├── rule_type (threshold, transaction, daily_summary)
├── conditions (JSON)
├── is_active (default: true)
└── created_at / updated_at

ProcessedEvent
├── id (PK)
├── event_id (unique — idempotency key)
├── event_type
├── status (processed, failed)
└── processed_at
```

## Steps to Run Locally

### Prerequisites
- Python 3.11+
- PostgreSQL with `acumen_notification` database created
- RabbitMQ (for event consumption and Celery broker)
- Redis (for Celery result backend)

### Option 1: Docker (Recommended)
```bash
# From the project root (with docker-compose.yml)
# Starts the Flask app, Celery worker, Celery beat, and consumer
docker-compose up --build notification_service celery_worker celery_beat notification_consumer
```

### Option 2: Standalone
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export FLASK_ENV=development
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=your_user
export POSTGRES_PASSWORD=your_password
export NOTIFICATION_DB=acumen_notification
export JWT_SECRET=your-secret-key
export RABBITMQ_HOST=localhost
export CELERY_BROKER_URL=amqp://admin:admin123@localhost:5672//
export CELERY_RESULT_BACKEND=redis://localhost:6379/1
export PYTHONPATH=/path/to/notification_service

# Terminal 1: Flask app
gunicorn wsgi:app --bind 0.0.0.0:5002 --workers 4

# Terminal 2: Celery worker
celery -A celery_app.celery worker --loglevel=info --concurrency=4

# Terminal 3: Celery beat
celery -A celery_app.celery beat --loglevel=info

# Terminal 4: Event consumer
python consumer.py
```

### Seed Demo Data
```bash
docker exec -it acumen_notification_service python seed.py
```

### Verify
```bash
curl http://localhost:5002/health
# {"service": "notification-service", "status": "healthy", "database": "connected"}
```

## API Endpoints

### Notifications (requires JWT via Gateway)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/notifications` | List user notifications (paginated) |
| PATCH | `/api/notifications/:id/read` | Mark notification as read |
| PATCH | `/api/notifications/read-all` | Mark all notifications as read |

### Preferences (requires JWT via Gateway)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/preferences` | Get notification preferences |
| PUT | `/api/preferences` | Update preferences (channels, quiet hours) |

### Rules (requires JWT via Gateway)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/rules` | List notification rules |
| POST | `/api/rules` | Create a new rule |
| PUT | `/api/rules/:id` | Update a rule |
| DELETE | `/api/rules/:id` | Delete a rule |

## Event Processing Pipeline

```
1. RabbitMQ receives event (e.g., "transaction.created")
       │
2. consumer.py picks up the message
       │
3. Checks ProcessedEvent table (idempotency)
       │
4. Dispatches Celery task: process_event.delay(event_data)
       │
5. Celery worker evaluates all active rules for the user
       │
6. Matching rules → create Notification records
       │
7. send_notification_task → mock delivery (email/SMS/push)
       │
8. Notification status updated to "sent"
```

### Error Handling
- **Task failure**: Celery retries up to 3 times with exponential backoff
- **Unprocessable messages**: Routed to Dead Letter Queue (DLQ)
- **Failed deliveries**: `retry_failed_task` (Celery Beat, every 5 min) retries failed notifications
- **Pending notifications**: `send_pending_task` (Celery Beat, every 10 sec) sends pending notifications

## CI/CD (Jenkins)

Pipeline stages: `Checkout → Install → Lint → Test → Docker Build → Deploy (+ workers)`

The deploy stage restarts all notification-related containers: Flask app, Celery worker, Celery beat, and consumer.

See [Jenkinsfile](./Jenkinsfile) for full pipeline definition.

## Related Services

- [API Gateway](https://github.com/lazuardi21/AcumenAPIGateway) — Central entry point, auth, rate limiting
- [Portfolio Service](https://github.com/lazuardi21/AcumenPortfolio) — Publishes transaction events consumed by this service
