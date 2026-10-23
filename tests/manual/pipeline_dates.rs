// Usage: pipeline_dates GENERATED_OUTPUT_DIR EXPECTED_DATES_JSON
// Run after the actual pipeline with controlled source responses. Requires jq.
use std::{env, path::Path, process::Command};

fn main() {
    let args: Vec<String> = env::args().collect();
    assert_eq!(args.len(), 3, "supply generated output and expected dates");
    let output = Path::new(&args[1]);
    let status = Command::new("jq")
        .args([
            "-e", "-s", "--slurpfile", "expected", &args[2],
            "add | length as $count | map({key: .id, value: {published_date, year}}) | from_entries | length == $count and . == $expected[0]",
        ])
        .arg(output.join("papers_db.json"))
        .arg(output.join("conferences_db.json"))
        .arg(output.join("journals_db.json"))
        .status()
        .expect("jq must be installed for this manual check");
    assert!(
        status.success(),
        "generated dates differ from source fixture expectations"
    );
    println!("pipeline publication dates match the source fixture");
}
