use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Simple TF-IDF style embedding index for semantic search.
/// In production, replace with sentence-transformer embeddings.
/// Stores term frequency vectors per document.
pub struct EmbeddingIndex {
    /// doc_id → term frequencies
    documents: Arc<RwLock<HashMap<String, HashMap<String, f32>>>>,
    /// term → document frequency (how many docs contain it)
    doc_freq: Arc<RwLock<HashMap<String, usize>>>,
}

impl EmbeddingIndex {
    pub fn new() -> Self {
        Self {
            documents: Arc::new(RwLock::new(HashMap::new())),
            doc_freq: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Index a document by its text content
    pub async fn index(&self, doc_id: impl Into<String>, text: &str) {
        let doc_id = doc_id.into();
        let tf = term_frequencies(text);

        let mut doc_freq = self.doc_freq.write().await;
        for term in tf.keys() {
            *doc_freq.entry(term.clone()).or_insert(0) += 1;
        }
        drop(doc_freq);

        self.documents.write().await.insert(doc_id, tf);
    }

    /// Remove a document from the index
    pub async fn remove(&self, doc_id: &str) {
        let mut docs = self.documents.write().await;
        if let Some(tf) = docs.remove(doc_id) {
            let mut df = self.doc_freq.write().await;
            for term in tf.keys() {
                if let Some(count) = df.get_mut(term) {
                    *count = count.saturating_sub(1);
                    if *count == 0 {
                        df.remove(term);
                    }
                }
            }
        }
    }

    /// Search for the top-k most relevant documents using TF-IDF cosine similarity
    pub async fn search(&self, query: &str, top_k: usize) -> Vec<(String, f32)> {
        let query_tf = term_frequencies(query);
        let docs = self.documents.read().await;
        let df = self.doc_freq.read().await;
        let n_docs = docs.len().max(1) as f32;

        let mut scores: Vec<(String, f32)> = docs
            .iter()
            .map(|(doc_id, doc_tf)| {
                let score = cosine_tfidf(&query_tf, doc_tf, &df, n_docs);
                (doc_id.clone(), score)
            })
            .filter(|(_, s)| *s > 0.0)
            .collect();

        scores.sort_by(|a, b| {
            b.1.partial_cmp(&a.1)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        scores.truncate(top_k);
        scores
    }
}

impl Default for EmbeddingIndex {
    fn default() -> Self {
        Self::new()
    }
}

fn term_frequencies(text: &str) -> HashMap<String, f32> {
    let mut counts: HashMap<String, f32> = HashMap::new();
    let total: f32 = text.split_whitespace().count() as f32;
    for word in text.split_whitespace() {
        let term = word
            .to_lowercase()
            .trim_matches(|c: char| !c.is_alphanumeric())
            .to_string();
        if !term.is_empty() {
            *counts.entry(term).or_insert(0.0) += 1.0 / total.max(1.0);
        }
    }
    counts
}

fn cosine_tfidf(
    query_tf: &HashMap<String, f32>,
    doc_tf: &HashMap<String, f32>,
    df: &HashMap<String, usize>,
    n_docs: f32,
) -> f32 {
    let mut dot = 0.0f32;
    let mut query_norm = 0.0f32;
    let mut doc_norm = 0.0f32;

    for (term, q_tf) in query_tf {
        let idf =
            ((n_docs + 1.0) / (df.get(term).copied().unwrap_or(0) as f32 + 1.0)).ln() + 1.0;
        let q_tfidf = q_tf * idf;
        query_norm += q_tfidf * q_tfidf;

        if let Some(d_tf) = doc_tf.get(term) {
            let d_tfidf = d_tf * idf;
            dot += q_tfidf * d_tfidf;
        }
    }

    for (term, d_tf) in doc_tf {
        let idf =
            ((n_docs + 1.0) / (df.get(term).copied().unwrap_or(0) as f32 + 1.0)).ln() + 1.0;
        doc_norm += (d_tf * idf) * (d_tf * idf);
    }

    let denom = query_norm.sqrt() * doc_norm.sqrt();
    if denom == 0.0 {
        0.0
    } else {
        dot / denom
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn index_and_search() {
        let idx = EmbeddingIndex::new();
        idx.index("doc1", "cats are fluffy animals that meow").await;
        idx.index("doc2", "dogs are loyal animals that bark").await;
        idx.index("doc3", "the weather is sunny today nice").await;

        let results = idx.search("fluffy cats", 2).await;
        assert!(!results.is_empty());
        assert_eq!(results[0].0, "doc1");
    }

    #[tokio::test]
    async fn remove_from_index() {
        let idx = EmbeddingIndex::new();
        idx.index("doc1", "cats meow loudly").await;
        idx.remove("doc1").await;

        let results = idx.search("cats", 5).await;
        assert!(results.is_empty());
    }

    #[tokio::test]
    async fn empty_index_returns_empty() {
        let idx = EmbeddingIndex::new();
        let results = idx.search("anything", 5).await;
        assert!(results.is_empty());
    }
}
