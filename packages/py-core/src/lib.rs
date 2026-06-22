// Pure Rust logic — no pyo3 dependency, always testable with `cargo test`.
pub fn greet(name: &str) -> String {
    format!("Hello from Rust, {}!", name)
}

// PyO3 wiring — compiled only when building the Python extension.
#[cfg(feature = "extension-module")]
use pyo3::prelude::*;

#[cfg(feature = "extension-module")]
#[pyfunction]
fn py_greet(name: &str) -> String {
    greet(name)
}

#[cfg(feature = "extension-module")]
#[pymodule]
fn py_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(py_greet, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_greet() {
        assert_eq!(greet("World"), "Hello from Rust, World!");
    }

    #[test]
    fn test_greet_empty_name() {
        assert_eq!(greet(""), "Hello from Rust, !");
    }
}
