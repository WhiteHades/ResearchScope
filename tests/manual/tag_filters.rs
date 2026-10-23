// Run against a disposable local API after loading tag_filters.sql.
use std::{
    io::{Read, Write},
    net::TcpStream,
    time::Duration,
};

fn query(source: &str, tag: &str, page: usize) -> String {
    let encoded: String = tag.bytes().map(|b| format!("%{b:02X}")).collect();
    let mut stream = TcpStream::connect("127.0.0.1:8000").expect("local API");
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .unwrap();
    stream
        .set_write_timeout(Some(Duration::from_secs(5)))
        .unwrap();
    write!(stream, "GET /papers?source_type={source}&tag={encoded}&page={page}&page_size=2&sort_by=title HTTP/1.1\r\nHost: 127.0.0.1:8000\r\nConnection: close\r\n\r\n").unwrap();
    let mut response = String::new();
    stream
        .take(1024 * 1024 + 1)
        .read_to_string(&mut response)
        .unwrap();
    assert!(response.len() <= 1024 * 1024);
    assert!(response.starts_with("HTTP/1.1 200 "), "{tag}: {response}");
    response.split_once("\r\n\r\n").unwrap().1.to_owned()
}

fn main() {
    let cases: &[(&[&str], &[&str])] = &[
        (
            &["IR", "Information Retrieval"],
            &["ir-both", "ir-long", "ir-short"],
        ),
        (
            &["ASR", "Speech Recognition", "Speech recognition"],
            &["asr-case", "asr-long", "asr-short"],
        ),
        (
            &["TTS", "Speech Synthesis", "Speech synthesis"],
            &["tts-case", "tts-long", "tts-short"],
        ),
        (
            &["NLG", "Natural Language Generation"],
            &["nlg-long", "nlg-short"],
        ),
        (
            &["LLMs", "Large Language Models"],
            &["llm-long", "llm-short"],
        ),
        (&["Speech"], &["speech-only"]),
        (&["Speech separation"], &["separation-only"]),
        (&["constructor"], &["constructor-only"]),
        (&["asr", "missing", "' OR 1=1 --"], &[]),
    ];
    let mut checked = 0;
    for source in ["preprint", "conference", "journal"] {
        for (aliases, ids) in cases {
            for tag in *aliases {
                for page in 1..=2 {
                    let body = query(source, tag, page);
                    assert!(
                        body.contains(&format!("\"total\":{},", ids.len())),
                        "{source}/{tag}: {body}"
                    );
                    let expected: Vec<_> = ids.iter().skip((page - 1) * 2).take(2).collect();
                    assert_eq!(body.matches("\"id\":").count(), expected.len());
                    for id in expected {
                        assert!(
                            body.contains(&format!("\"id\":\"{source}-{id}\"")),
                            "{source}/{tag}: {body}"
                        );
                    }
                    checked += 1;
                }
            }
        }
    }
    println!("{checked} local API label and pagination checks passed");
}
