import { useEffect, useRef, useState } from "react";

const API = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const MAX_BYTES = 10 * 1024 * 1024;
const ALLOWED = [".pdf", ".docx"];

const STATUS_TEXT = {
  uploading: "Uploading to S3",
  awaiting_upload: "Waiting for the upload to arrive",
  uploaded: "Upload received",
  queued: "Queued by the upload trigger",
  routing: "Orchestrator is choosing an agent",
  processing: "Processing",
  done: "Done",
  failed: "Failed",
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { "content-type": "application/json", ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.Message || `Request failed (${res.status})`);
  return data;
}

async function runJob(file, mode, onUpdate) {
  const { job_id, upload_url, content_type } = await api("/upload-url", {
    method: "POST",
    body: JSON.stringify({ file_name: file.name, mode }),
  });
  onUpdate({ jobId: job_id });

  const put = await fetch(upload_url, { method: "PUT", headers: { "Content-Type": content_type }, body: file });
  if (!put.ok) throw new Error(`Upload to S3 failed (${put.status}). Try again.`);

  let finished = false;
  const poll = (async () => {
    for (let i = 0; i < 200 && !finished; i++) {
      try {
        const job = await api(`/status?job_id=${job_id}`);
        onUpdate({ job });
        if (job.status === "done" || job.status === "failed") return;
      } catch {
        /* keep polling */
      }
      await sleep(1500);
    }
  })();

  if (mode === "sync") {
    try {
      await api("/process", { method: "POST", body: JSON.stringify({ job_id }) });
    } finally {
      finished = true;
      onUpdate({ job: await api(`/status?job_id=${job_id}`) });
    }
  } else {
    await poll;
    finished = true;
  }
}

function laneOf(msg) {
  if (/^Delegated to .* on Databricks/.test(msg)) return "cross-dbx";
  if (/^Delegated to .* on AWS/.test(msg)) return "cross-aws";
  if (/^databricks-pdf-agent/.test(msg)) return "databricks";
  return "aws";
}

function Lanes({ events }) {
  if (!events || events.length === 0) return null;
  return (
    <div className="lanes" role="list" aria-label="What the agents did, in order">
      <div className="lane-head aws" aria-hidden="true">AWS</div>
      <div className="lane-head dbx" aria-hidden="true">Databricks</div>
      {events.map((e, i) => {
        const lane = laneOf(e.msg);
        if (lane.startsWith("cross")) {
          return (
            <div key={i} role="listitem" className={`handoff ${lane === "cross-dbx" ? "to-dbx" : "to-aws"}`}>
              <span className="handoff-line" aria-hidden="true" />
              <span className="handoff-text">{e.msg}</span>
            </div>
          );
        }
        return (
          <div key={i} role="listitem" className={`event ${lane}`}>
            <span className="dot" aria-hidden="true" />
            <span>{e.msg}</span>
          </div>
        );
      })}
    </div>
  );
}

function TypedText({ text }) {
  const words = (text || "").split(" ");
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setCount(words.length);
      return;
    }
    setCount(0);
    const id = setInterval(() => {
      setCount((c) => {
        if (c >= words.length) {
          clearInterval(id);
          return c;
        }
        return c + 1;
      });
    }, 30);
    return () => clearInterval(id);
  }, [text]);
  return <p className="summary">{words.slice(0, count).join(" ")}</p>;
}

function Result({ job }) {
  const r = job.result || {};
  const cloud = job.assigned_cloud || (String(r.processed_by || "").startsWith("databricks") ? "Databricks" : "AWS");
  const groups = [
    ["People", "people"],
    ["Organizations", "organizations"],
    ["Dates", "dates"],
    ["Amounts", "amounts"],
  ]
    .map(([label, key]) => [label, (r.entities && r.entities[key]) || []])
    .filter(([, values]) => values.length > 0);

  return (
    <section className="result" aria-label="Result">
      <p className="result-meta">
        <span className={`badge ${cloud === "Databricks" ? "dbx" : "aws"}`}>{cloud}</span>
        <span>
          {r.document_type ? `${r.document_type[0].toUpperCase()}${r.document_type.slice(1)}` : "Document"}, processed by{" "}
          {r.processed_by}
        </span>
      </p>
      <TypedText text={r.summary || job.summary} />
      {r.key_points && r.key_points.length > 0 && (
        <>
          <h3>Key points</h3>
          <ul className="points">
            {r.key_points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </>
      )}
      {groups.length > 0 && (
        <dl className="entities">
          {groups.map(([label, values]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{values.join(", ")}</dd>
            </div>
          ))}
        </dl>
      )}
      {r.stored_in && <p className="stored">Saved to {r.stored_in}</p>}
    </section>
  );
}

function JobCard({ item }) {
  const job = item.job || {};
  const status = item.error ? "failed" : job.status || "uploading";
  let text = STATUS_TEXT[status] || status;
  if (status === "processing" && job.assigned_cloud) text = `Processing on ${job.assigned_cloud}`;
  const modeText =
    item.mode === "sync"
      ? "Synchronous: the page waits for the answer"
      : "Asynchronous: the upload trigger starts the work";

  return (
    <article className="job">
      <header className="job-head">
        <div>
          <p className="file">{item.fileName}</p>
          <p className="mode">{modeText}</p>
        </div>
        <p className={`status s-${status}`} aria-live="polite">
          {text}
        </p>
      </header>
      <Lanes events={job.events} />
      {item.error && <p className="error">{item.error}</p>}
      {!item.error && status === "failed" && job.error && <p className="error">{job.error}</p>}
      {status === "done" && job.result && <Result job={job} />}
    </article>
  );
}

export default function App() {
  const [items, setItems] = useState([]);
  const [file, setFile] = useState(null);
  const [mode, setMode] = useState("sync");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const inputRef = useRef(null);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items]);

  function pick(e) {
    const f = e.target.files && e.target.files[0];
    setFormError("");
    if (!f) return;
    const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED.includes(ext)) {
      setFormError("Choose a .pdf or .docx file.");
      setFile(null);
      return;
    }
    if (f.size > MAX_BYTES) {
      setFormError("This file is larger than 10 MB. Choose a smaller file.");
      setFile(null);
      return;
    }
    setFile(f);
  }

  async function submit() {
    if (!file || busy) return;
    const id = crypto.randomUUID();
    const update = (patch) => setItems((all) => all.map((it) => (it.id === id ? { ...it, ...patch } : it)));
    setItems((all) => [...all, { id, fileName: file.name, mode }]);
    setBusy(true);
    const current = file;
    setFile(null);
    if (inputRef.current) inputRef.current.value = "";
    try {
      await runJob(current, mode, update);
    } catch (err) {
      update({ error: err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="top">
        <h1>Document agents across AWS and Databricks</h1>
        <p className="lede">
          Upload a PDF or Word file. An orchestrator agent on AWS reads the agent registry and hands the file to the
          right agent over MCP: Word files stay on AWS, PDFs go to Databricks.
        </p>
      </header>

      <main className="thread">
        {items.length === 0 && <p className="empty">No documents yet. Choose a file below to start.</p>}
        {items.map((it) => (
          <JobCard key={it.id} item={it} />
        ))}
        <div ref={endRef} />
      </main>

      <footer className="composer">
        <div className="composer-inner">
          <div className="row">
            <label className="file-btn">
              <input ref={inputRef} type="file" accept=".pdf,.docx" onChange={pick} disabled={busy} />
              Choose file
            </label>
            <span className="picked">{file ? file.name : "No file chosen"}</span>
          </div>
          <fieldset className="modes" disabled={busy}>
            <legend>How to run it</legend>
            <label>
              <input type="radio" name="mode" checked={mode === "sync"} onChange={() => setMode("sync")} />
              Wait for the result
            </label>
            <label>
              <input type="radio" name="mode" checked={mode === "async"} onChange={() => setMode("async")} />
              Run in the background
            </label>
          </fieldset>
          {formError && (
            <p className="error" role="alert">
              {formError}
            </p>
          )}
          {!API && <p className="error">The API address is missing. Rebuild with VITE_API_URL set.</p>}
          <button className="go" onClick={submit} disabled={!file || busy}>
            {busy ? "Processing…" : "Process document"}
          </button>
        </div>
      </footer>
    </div>
  );
}
