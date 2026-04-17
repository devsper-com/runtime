//! Provider credential management — OS keychain storage and env-var injection.

use std::io::{self, Write};

const SERVICE: &str = "devsper";

/// A single credential field definition.
struct Field {
    name: &'static str,
    env_var: &'static str,
    secret: bool,
    optional: bool,
    default: Option<&'static str>,
}

/// A provider with its fields.
struct Provider {
    name: &'static str,
    fields: &'static [Field],
}

macro_rules! field {
    ($name:expr, $env:expr, secret) => {
        Field { name: $name, env_var: $env, secret: true, optional: false, default: None }
    };
    ($name:expr, $env:expr) => {
        Field { name: $name, env_var: $env, secret: false, optional: false, default: None }
    };
    ($name:expr, $env:expr, optional, $default:expr) => {
        Field { name: $name, env_var: $env, secret: false, optional: true, default: Some($default) }
    };
    ($name:expr, $env:expr, secret, optional, $default:expr) => {
        Field { name: $name, env_var: $env, secret: true, optional: true, default: Some($default) }
    };
}

static PROVIDERS: &[Provider] = &[
    Provider {
        name: "anthropic",
        fields: &[field!("api_key", "ANTHROPIC_API_KEY", secret)],
    },
    Provider {
        name: "openai",
        fields: &[field!("api_key", "OPENAI_API_KEY", secret)],
    },
    Provider {
        name: "github",
        fields: &[field!("token", "GITHUB_TOKEN", secret)],
    },
    Provider {
        name: "zai",
        fields: &[
            field!("api_key", "ZAI_API_KEY", secret),
            field!("base_url", "ZAI_BASE_URL", optional, "https://api.z.ai/v1"),
        ],
    },
    Provider {
        name: "azure-openai",
        fields: &[
            field!("api_key", "AZURE_OPENAI_API_KEY", secret),
            field!("endpoint", "AZURE_OPENAI_ENDPOINT"),
            field!("deployment", "AZURE_OPENAI_DEPLOYMENT"),
            field!("api_version", "AZURE_OPENAI_API_VERSION", optional, "2024-02-01"),
        ],
    },
    Provider {
        name: "azure-foundry",
        fields: &[
            field!("api_key", "AZURE_FOUNDRY_API_KEY", secret),
            field!("endpoint", "AZURE_FOUNDRY_ENDPOINT"),
            field!("deployment", "AZURE_FOUNDRY_DEPLOYMENT"),
        ],
    },
    Provider {
        name: "litellm",
        fields: &[
            field!("base_url", "LITELLM_BASE_URL"),
            field!("api_key", "LITELLM_API_KEY", secret, optional, ""),
        ],
    },
    Provider {
        name: "ollama",
        fields: &[field!("host", "OLLAMA_HOST", optional, "http://localhost:11434")],
    },
    Provider {
        name: "lmstudio",
        fields: &[
            field!("base_url", "LMSTUDIO_BASE_URL", optional, "http://localhost:1234"),
            field!("api_key", "LMSTUDIO_API_KEY", secret, optional, ""),
        ],
    },
];

fn find_provider(name: &str) -> Option<&'static Provider> {
    PROVIDERS.iter().find(|p| p.name == name)
}

fn keychain_key(provider: &str, field: &str) -> String {
    format!("{provider}:{field}")
}

/// Read a value from the OS keychain.
fn keychain_get(provider: &str, field: &str) -> Option<String> {
    let key = keychain_key(provider, field);
    keyring::Entry::new(SERVICE, &key)
        .ok()
        .and_then(|e| e.get_password().ok())
}

/// Write a value to the OS keychain.
pub fn set_field(provider: &str, field: &str, value: &str) {
    let key = keychain_key(provider, field);
    match keyring::Entry::new(SERVICE, &key) {
        Ok(entry) => {
            if let Err(e) = entry.set_password(value) {
                eprintln!("Warning: could not save {key} to keychain: {e}");
            }
        }
        Err(e) => eprintln!("Warning: keychain entry error for {key}: {e}"),
    }
}

/// Interactive prompt for each field of a provider.
pub fn credentials_set(provider: &str) {
    let Some(p) = find_provider(provider) else {
        eprintln!("Unknown provider '{provider}'. Available: {}", provider_names());
        return;
    };

    println!("Setting credentials for '{provider}':");
    for field in p.fields {
        let prompt = if let Some(default) = field.default {
            if default.is_empty() {
                format!("  {} (optional, press Enter to skip): ", field.name)
            } else {
                format!("  {} [default: {}]: ", field.name, default)
            }
        } else {
            format!("  {}: ", field.name)
        };

        let value = if field.secret {
            rpassword::prompt_password(&prompt).unwrap_or_default()
        } else {
            print!("{prompt}");
            io::stdout().flush().ok();
            let mut buf = String::new();
            io::stdin().read_line(&mut buf).ok();
            buf.trim().to_string()
        };

        let value = if value.is_empty() {
            if let Some(default) = field.default {
                if default.is_empty() {
                    continue; // skip optional with no default
                }
                default.to_string()
            } else {
                eprintln!("  Skipping empty required field '{}'", field.name);
                continue;
            }
        } else {
            value
        };

        set_field(provider, field.name, &value);
        println!("  Saved {}.", field.name);
    }
    println!("Done.");
}

/// Print a status table for all providers and their fields.
pub fn credentials_list() {
    let col_w = [16usize, 12, 8, 24];
    let sep = format!(
        "+-{:-<w0$}-+-{:-<w1$}-+-{:-<w2$}-+-{:-<w3$}-+",
        "", "", "", "",
        w0 = col_w[0], w1 = col_w[1], w2 = col_w[2], w3 = col_w[3],
    );

    println!("{sep}");
    println!(
        "| {:<w0$} | {:<w1$} | {:<w2$} | {:<w3$} |",
        "provider", "field", "status", "env_var",
        w0 = col_w[0], w1 = col_w[1], w2 = col_w[2], w3 = col_w[3],
    );
    println!("{sep}");

    for p in PROVIDERS {
        for field in p.fields {
            let in_keychain = keychain_get(p.name, field.name).is_some();
            let in_env = std::env::var(field.env_var).is_ok();

            let status = if in_keychain {
                "keychain"
            } else if in_env {
                "env"
            } else if field.optional {
                "default"
            } else {
                "unset"
            };

            println!(
                "| {:<w0$} | {:<w1$} | {:<w2$} | {:<w3$} |",
                p.name, field.name, status, field.env_var,
                w0 = col_w[0], w1 = col_w[1], w2 = col_w[2], w3 = col_w[3],
            );
        }
    }
    println!("{sep}");
}

/// Remove all keychain entries for a provider.
pub fn credentials_remove(provider: &str) {
    let Some(p) = find_provider(provider) else {
        eprintln!("Unknown provider '{provider}'. Available: {}", provider_names());
        return;
    };

    for field in p.fields {
        let key = keychain_key(p.name, field.name);
        if let Ok(entry) = keyring::Entry::new(SERVICE, &key) {
            match entry.delete_credential() {
                Ok(_) => println!("Removed {key}"),
                Err(keyring::Error::NoEntry) => {} // already gone
                Err(e) => eprintln!("Warning: could not remove {key}: {e}"),
            }
        }
    }
    println!("Credentials for '{provider}' removed.");
}

/// Inject keychain credentials into env vars (does not overwrite existing env vars).
pub fn inject_credentials() {
    for p in PROVIDERS {
        for field in p.fields {
            // Skip if env var already set
            if std::env::var(field.env_var).is_ok() {
                continue;
            }
            if let Some(value) = keychain_get(p.name, field.name) {
                if !value.is_empty() {
                    // SAFETY: single-threaded at this point; called before any async work.
                    unsafe { std::env::set_var(field.env_var, &value) };
                }
            }
        }
    }
}

fn provider_names() -> String {
    PROVIDERS.iter().map(|p| p.name).collect::<Vec<_>>().join(", ")
}
