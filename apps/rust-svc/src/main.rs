fn startup_message() -> String {
    format!("rust-svc v{} starting", env!("CARGO_PKG_VERSION"))
}

fn main() {
    println!("{}", startup_message());
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_startup_message_contains_version() {
        let msg = startup_message();
        assert!(msg.contains("rust-svc"));
        assert!(msg.contains(env!("CARGO_PKG_VERSION")));
    }
}
