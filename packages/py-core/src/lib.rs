use pyo3::prelude::*;

#[pyfunction]
fn greet(name: &str) -> String {
    format!("Hello from Rust, {}!", name)
}

#[pymodule]
fn py_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(greet, m)?)?;
    Ok(())
}
