fn main() {
    // On macOS, Python extension modules (.so/.dylib) must use -undefined dynamic_lookup
    // so that Python C API symbols are resolved at load time by the Python interpreter.
    // This is required for pyo3 extension-module builds with abi3 on macOS.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        println!("cargo:rustc-link-arg=-undefined");
        println!("cargo:rustc-link-arg=dynamic_lookup");
    }
}
