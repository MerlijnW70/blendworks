use std::fmt;

pub const INVALID_ARGUMENT: i32 = 1;
pub const CYCLE: i32 = 2;
pub const PANIC: i32 = 3;

#[derive(Debug, Clone, PartialEq)]
pub struct KernelError {
    pub code: i32,
    pub message: String,
}

impl KernelError {
    pub fn invalid(message: impl Into<String>) -> Self {
        KernelError { code: INVALID_ARGUMENT, message: message.into() }
    }

    pub fn cycle(message: impl Into<String>) -> Self {
        KernelError { code: CYCLE, message: message.into() }
    }

    pub fn panic(message: impl Into<String>) -> Self {
        KernelError { code: PANIC, message: message.into() }
    }
}

impl fmt::Display for KernelError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

pub type KernelResult<T> = Result<T, KernelError>;

pub fn check(condition: bool, message: impl FnOnce() -> String) -> KernelResult<()> {
    if condition {
        Ok(())
    } else {
        Err(KernelError::invalid(message()))
    }
}
