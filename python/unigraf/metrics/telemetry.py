# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handles all OpenTelemetry SDK setup and metric creation."""

import logging
import socket
from typing import Any, Callable
import urllib.error
import urllib.request

import grpc
from grpc_interceptor import ServerInterceptor
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource


class MetricsService:
    """
    Manages OpenTelemetry setup, provider, and instrument creation.
    Provides safe methods for metric recording.

    Will perform a health check on the OTLP endpoint upon initialization.
    If the endpoint is not reachable, the service will be disabled
    and no metrics will be exported.
    """

    OTLP_ENDPOINT = "http://opentelemetry-collector:4318/v1/metrics"
    SERVICE_NAME = "passport"
    EXPORT_INTERVAL_MS = 10000

    def __init__(
        self,
    ):
        """
        Initializes the OTel SDK and creates the required metrics.
        """
        # Set defaults to None. If init fails, these remain None,
        # and the "safe" record_ methods will simply return.
        self.meter = None
        self.request_counter = None

        try:
            urllib.request.urlopen(self.OTLP_ENDPOINT, timeout=2)
            logging.info(
                f"Successfully connected to OTel collector at {self.OTLP_ENDPOINT}"
            )
        except urllib.error.HTTPError as e:
            # HTTPError implies the server was reached but returned a non-200 code.
            # 405 (Method Not Allowed) is acceptable for a connectivity check.
            if e.code == 405:
                logging.info(
                    f"Successfully connected to OTel collector at {self.OTLP_ENDPOINT} (received 405, ignored)"
                )
            else:
                logging.warning(
                    f"Connected to OTel collector, but received error code: {e.code}"
                )
                return
        except (urllib.error.URLError, socket.timeout) as e:
            logging.warning(
                f"Could not connect to OTel collector at {self.OTLP_ENDPOINT}: {e}"
            )
            return

        try:
            exporter = OTLPMetricExporter(endpoint=self.OTLP_ENDPOINT)
            reader = PeriodicExportingMetricReader(
                exporter, export_interval_millis=self.EXPORT_INTERVAL_MS
            )
            resource = Resource(attributes={"service.name": self.SERVICE_NAME})
            provider = MeterProvider(metric_readers=[reader], resource=resource)
            metrics.set_meter_provider(provider)

            self.meter = metrics.get_meter("passport.library", "1.0.0")

            self.request_counter = self.meter.create_counter(
                name="passport.requests.total",
                description="Counts all completed gRPC requests by status.",
                unit="1",
            )

            logging.info(
                f"MetricsService initialized. Exporting to {self.OTLP_ENDPOINT}"
            )

        except Exception as e:
            # Make sure we disable telemetry.
            self.meter = None
            self.request_counter = None
            logging.error(f"Failed to initialize MetricsService SDK: {e}")

    def record_request(
        self, method_name: str, status_code: str, service_name: str
    ):
        """
        Safely increments the global request counter.

        This method will not raise an exception if the counter
        is not initialized or if the .add() call fails.
        """
        # No open telemetry exporter was found, don't log anything.
        if self.request_counter is None:
            return

        try:
            attributes = {
                "rpc.method": method_name,
                "rpc.status_code": status_code,
                "service.name": service_name,
            }
            self.request_counter.add(1, attributes)
        except Exception as e:
            logging.error(f"MetricsService: Failed to record request: {e}")


class GlobalMetricsInterceptor(ServerInterceptor):
    """
    A gRPC interceptor that manually counts all successful and failed requests.
    It can be filtered to only apply to a specific target service.
    """

    def __init__(
        self,
        metrics_service: MetricsService,
    ):
        """
        Initializes the interceptor.

        Args:
            metrics_service: The MetricsService instance.
        """
        self.metrics = metrics_service
        logging.info("GlobalMetricsInterceptor initialized.")

    def intercept(
        self,
        method: Callable,
        request: Any,
        context: grpc.ServicerContext,
        method_name: str,
    ) -> Any:

        # method_name is like "/package.Service/MethodName"
        # We extract "package.Service"
        try:
            # Split will produce ['', 'package.Service', 'MethodName']
            service_name = method_name.split("/")[1]
        except IndexError:
            service_name = "UNKNOWN_SERVICE"

        try:
            response = method(request, context)

            status_code = "OK"
            if hasattr(response, "err_code") and response.err_code != 0:
                status_code = "LOGICAL_ERROR"

            self.metrics.record_request(method_name, status_code, service_name)
            return response
        except grpc.RpcError as e:
            status_code = e.code().name
            logging.warning(
                f"Interceptor: gRPC error in {method_name}: {status_code}"
            )
            self.metrics.record_request(method_name, status_code, service_name)
            raise e

        except Exception as e:
            status_code = "UNKNOWN_ERROR"
            logging.error(
                f"Interceptor: Unknown error in {method_name}: {e}",
                exc_info=True,
            )
            self.metrics.record_request(method_name, status_code, service_name)
            raise e
