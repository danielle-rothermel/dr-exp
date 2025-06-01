export async function fetchJobs() {
  const resp = await fetch('http://localhost:8000/jobs');
  if (!resp.ok) {
    throw new Error(`API error ${resp.status}`);
  }
  return resp.json();
}

export async function fetchJobConfig(jobId) {
  const resp = await fetch(`http://localhost:8000/config/${jobId}`);
  if (!resp.ok) {
    throw new Error(`API error ${resp.status}`);
  }
  return resp.json();
}

export async function fetchJobMetrics(jobId) {
  const resp = await fetch(`http://localhost:8000/metrics/${jobId}`);
  if (!resp.ok) {
    throw new Error(`API error ${resp.status}`);
  }
  return resp.json();
}
