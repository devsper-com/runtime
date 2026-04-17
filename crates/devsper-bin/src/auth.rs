//! Authentication helpers — GitHub device flow and provider status.

use crate::credentials;

/// GitHub OAuth App client_id.
/// TODO: Replace with your own GitHub OAuth App client_id from https://github.com/settings/developers
/// Or set the DEVSPER_GITHUB_CLIENT_ID environment variable to override.
const GITHUB_CLIENT_ID_DEFAULT: &str = "Ov23li4your_client_id";

const DEVICE_CODE_URL: &str = "https://github.com/login/device/code";
const TOKEN_URL: &str = "https://github.com/login/oauth/access_token";
const SCOPE: &str = "read:user";
const TIMEOUT_SECONDS: u64 = 900;

/// Run the GitHub device authorization flow and store the resulting token.
pub async fn auth_github() -> anyhow::Result<()> {
    let client_id = std::env::var("DEVSPER_GITHUB_CLIENT_ID")
        .unwrap_or_else(|_| GITHUB_CLIENT_ID_DEFAULT.to_string());

    if client_id == GITHUB_CLIENT_ID_DEFAULT {
        eprintln!(
            "Warning: using placeholder GitHub client_id. \
             Set DEVSPER_GITHUB_CLIENT_ID or edit credentials.rs with your OAuth App client_id."
        );
    }

    let client = reqwest::Client::new();

    // Step 1: request device + user codes
    let resp = client
        .post(DEVICE_CODE_URL)
        .header("Accept", "application/json")
        .form(&[("client_id", &client_id), ("scope", &SCOPE.to_string())])
        .send()
        .await?;

    if !resp.status().is_success() {
        anyhow::bail!("GitHub device code request failed: {}", resp.status());
    }

    let device_data: serde_json::Value = resp.json().await?;

    let user_code = device_data["user_code"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("Missing user_code in GitHub response"))?
        .to_string();
    let verification_uri = device_data["verification_uri"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("Missing verification_uri in GitHub response"))?
        .to_string();
    let device_code = device_data["device_code"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("Missing device_code in GitHub response"))?
        .to_string();
    let mut interval = device_data["interval"].as_u64().unwrap_or(5);
    let expires_in = device_data["expires_in"].as_u64().unwrap_or(TIMEOUT_SECONDS);

    println!();
    println!("=== GitHub Login ===");
    println!("Open this URL in your browser:");
    println!("  {verification_uri}");
    println!();
    println!("Enter this code:");
    println!("  {user_code}");
    println!();
    println!("Waiting for GitHub authorization...");

    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(expires_in);

    loop {
        if std::time::Instant::now() >= deadline {
            anyhow::bail!("Timed out waiting for GitHub authorization. Run the command again.");
        }

        tokio::time::sleep(std::time::Duration::from_secs(interval)).await;

        let token_resp = client
            .post(TOKEN_URL)
            .header("Accept", "application/json")
            .form(&[
                ("client_id", client_id.as_str()),
                ("device_code", device_code.as_str()),
                ("grant_type", "urn:ietf:params:oauth:grant-type:device_code"),
            ])
            .send()
            .await?;

        let token_data: serde_json::Value = token_resp.json().await?;

        match token_data["error"].as_str() {
            Some("authorization_pending") => continue,
            Some("slow_down") => {
                interval += 5;
                continue;
            }
            Some("expired_token") => {
                anyhow::bail!("Device code expired. Run the command again.");
            }
            Some("access_denied") => {
                anyhow::bail!("GitHub authorization was denied.");
            }
            Some(other) => {
                anyhow::bail!("GitHub authorization error: {other}");
            }
            None => {}
        }

        if let Some(token) = token_data["access_token"].as_str() {
            credentials::set_field("github", "token", token);
            // Also set env var for immediate use
            unsafe { std::env::set_var("GITHUB_TOKEN", token) };
            println!("GitHub authentication successful. Token stored in keychain.");
            return Ok(());
        }
    }
}

/// Print the authentication/configuration status of all 8 providers.
pub async fn auth_status() -> anyhow::Result<()> {
    use keyring::Entry;

    const SERVICE: &str = "devsper";

    struct ProviderStatus {
        name: &'static str,
        fields: &'static [(&'static str, &'static str)], // (field_name, env_var)
    }

    let providers: &[ProviderStatus] = &[
        ProviderStatus { name: "anthropic",    fields: &[("api_key", "ANTHROPIC_API_KEY")] },
        ProviderStatus { name: "openai",       fields: &[("api_key", "OPENAI_API_KEY")] },
        ProviderStatus { name: "github",       fields: &[("token", "GITHUB_TOKEN")] },
        ProviderStatus { name: "zai",          fields: &[("api_key", "ZAI_API_KEY"), ("base_url", "ZAI_BASE_URL")] },
        ProviderStatus { name: "azure-openai", fields: &[("api_key", "AZURE_OPENAI_API_KEY"), ("endpoint", "AZURE_OPENAI_ENDPOINT"), ("deployment", "AZURE_OPENAI_DEPLOYMENT")] },
        ProviderStatus { name: "azure-foundry",fields: &[("api_key", "AZURE_FOUNDRY_API_KEY"), ("endpoint", "AZURE_FOUNDRY_ENDPOINT"), ("deployment", "AZURE_FOUNDRY_DEPLOYMENT")] },
        ProviderStatus { name: "litellm",      fields: &[("base_url", "LITELLM_BASE_URL"), ("api_key", "LITELLM_API_KEY")] },
        ProviderStatus { name: "ollama",       fields: &[("host", "OLLAMA_HOST")] },
    ];

    let col_w = [16usize, 32, 12];
    let sep = format!(
        "+-{:-<w0$}-+-{:-<w1$}-+-{:-<w2$}-+",
        "", "", "",
        w0 = col_w[0], w1 = col_w[1], w2 = col_w[2],
    );

    println!("{sep}");
    println!(
        "| {:<w0$} | {:<w1$} | {:<w2$} |",
        "provider", "configured fields", "source",
        w0 = col_w[0], w1 = col_w[1], w2 = col_w[2],
    );
    println!("{sep}");

    for p in providers {
        let mut set_fields: Vec<String> = Vec::new();
        let mut source = "unset";

        for (field_name, env_var) in p.fields {
            let key = format!("{}:{}", p.name, field_name);
            let in_keychain = Entry::new(SERVICE, &key)
                .ok()
                .and_then(|e| e.get_password().ok())
                .is_some();
            let in_env = std::env::var(env_var).is_ok();

            if in_keychain {
                set_fields.push(field_name.to_string());
                source = "keychain";
            } else if in_env {
                set_fields.push(field_name.to_string());
                if source == "unset" {
                    source = "env";
                }
            }
        }

        let fields_str = if set_fields.is_empty() {
            "-".to_string()
        } else {
            set_fields.join(", ")
        };

        // Truncate fields_str if too long
        let fields_display = if fields_str.len() > col_w[1] {
            format!("{}...", &fields_str[..col_w[1].saturating_sub(3)])
        } else {
            fields_str
        };

        println!(
            "| {:<w0$} | {:<w1$} | {:<w2$} |",
            p.name, fields_display, source,
            w0 = col_w[0], w1 = col_w[1], w2 = col_w[2],
        );
    }
    println!("{sep}");
    Ok(())
}
