//! Budget helpers for worker-side request gating.

pub fn can_execute_with_budget(estimated_cost: Option<f64>, budget_remaining_usd: Option<f64>) -> bool {
    match (estimated_cost, budget_remaining_usd) {
        (_, None) => true,
        (None, Some(_)) => true,
        (Some(c), Some(rem)) => c <= rem,
    }
}
