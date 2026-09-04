//! Shipped desktop control labels — the 3.0 window draws these strings.

pub const EMAIL: &str = "E-Mail";
pub const PASSWORD: &str = "Passwort";
pub const SERVER: &str = "Server";
pub const RATE: &str = "Anschläge / 10 Minuten";
pub const CONNECT: &str = "Verbinden";
pub const START: &str = "Start Typing";
pub const STOP: &str = "Stop";
pub const REMAINING: &str = "Restzeile";
pub const MAX_SPEED: &str = "MAX Speed";
pub const AUTO_UPDATE: &str = "Automatisch aktualisieren";

pub fn all_controls() -> &'static [&'static str] {
    &[EMAIL, PASSWORD, SERVER, RATE, CONNECT, START, STOP, REMAINING, MAX_SPEED, AUTO_UPDATE]
}
