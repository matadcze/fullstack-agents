// WASM integration tests — run with: wasm-pack test --node packages/wasm-core
use wasm_bindgen_test::*;
use wasm_core::greet;

wasm_bindgen_test_configure!(run_in_node_experimental);

#[wasm_bindgen_test]
fn test_greet_wasm() {
    assert_eq!(greet("World"), "Hello from Rust/WASM, World!");
}
