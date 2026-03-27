//! OTEL bootstrap (best-effort).

pub fn init_otel() {
    let _endpoint = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT").ok();
    // Keep this lightweight for now; runtime tracing still goes through `tracing`.
}
