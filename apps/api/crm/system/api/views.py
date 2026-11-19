from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from crm.system import services
from crm.system.api.serializers import HealthSerializer, ReadinessSerializer


class HealthView(APIView):
    """Liveness: the process is up. Touches no external dependency."""

    permission_classes = [AllowAny]

    @extend_schema(operation_id="health", responses={200: HealthSerializer}, tags=["system"])
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class ReadinessView(APIView):
    """Readiness: PostgreSQL and Redis answer. Reports status only, never error text."""

    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="ready",
        responses={200: ReadinessSerializer, 503: ReadinessSerializer},
        tags=["system"],
    )
    def get(self, request: Request) -> Response:
        readiness = services.get_readiness()
        body = {
            "status": "ok" if readiness.ready else "unavailable",
            "checks": {
                "database": "ok" if readiness.database else "fail",
                "redis": "ok" if readiness.redis else "fail",
            },
        }
        return Response(body, status=200 if readiness.ready else 503)
