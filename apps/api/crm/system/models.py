from django.db import models


class Heartbeat(models.Model):
    """Last sign of life of a background component (technical table, no business data)."""

    component = models.CharField(max_length=64, unique=True)
    beats = models.PositiveBigIntegerField(default=0)
    last_beat_at = models.DateTimeField()

    class Meta:
        db_table = "system_heartbeat"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(component__regex=r"^[a-z0-9][a-z0-9_-]{0,63}$"),
                name="system_heartbeat_component_format",
            ),
        ]

    def __str__(self) -> str:
        return self.component
