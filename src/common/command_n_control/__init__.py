"""Generic RabbitMQ-based command-and-control bus.

Exchange topology (declared by ``src/app/scripts/init_rabbitmq.py``):

  exchange: command_n_control (topic, durable)
  dlx:      command_n_control_dlx  (direct, durable)
  dlq:      command_n_control_dlq  (durable classic queue bound to DLX)
  queues:   cnc.<container_name> — one per producer/daemon

Routing key convention:
  command_n_control.<container_name>
  e.g.  command_n_control.github-producer

Message format (CommandEnvelope):
  {
    "command_id": "uuid4",
    "command_type": "scan",
    "target": "github-producer",
    "parameters": {...},
    "issued_at": "2026-07-29T12:00:00Z"
  }
"""

from common.command_n_control.models import CommandEnvelope, CommandStatusUpdate
from common.command_n_control.publisher import CommandPublisher

__all__ = [
    "CommandEnvelope",
    "CommandStatusUpdate",
    "CommandPublisher",
]