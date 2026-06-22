use wasm_bindgen::prelude::*;

// Pure Rust core — testable on any platform with `cargo test`.
pub fn greet_inner(name: &str) -> String {
    format!("Hello from Rust/WASM, {}!", name)
}

// WASM-exported function.
#[wasm_bindgen]
pub fn greet(name: &str) -> String {
    greet_inner(name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_greet_inner() {
        assert_eq!(greet_inner("World"), "Hello from Rust/WASM, World!");
    }

    #[test]
    fn test_greet_inner_empty() {
        assert_eq!(greet_inner(""), "Hello from Rust/WASM, !");
    }
}
