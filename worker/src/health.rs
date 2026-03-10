//! Health checker — ping Redis, check subsystems.

use crate::error::Result;

pub struct HealthChecker;

impl HealthChecker {
    pub async fn check_redis(redis: &mut redis::aio::ConnectionManager) -> Result<bool> {
        let s: String = redis::cmd("PING")
            .query_async(redis)
            .await
            .map_err(crate::error::HivemindError::from)?;
        Ok(s == "PONG")
    }
}
