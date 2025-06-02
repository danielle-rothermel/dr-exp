/**
 * Retrieve the list of jobs from the backend API.
 *
 * @returns {Promise<Array>} Array of job objects.
 */
export async function fetchJobs() {
  const resp = await fetch('http://localhost:8000/jobs');
  if (!resp.ok) {
    throw new Error(`API error ${resp.status}`);
  }
  return resp.json();
}

/**
 * Fetch the configuration for a specific job.
 *
 * @param {string|number} jobId - Identifier for the job.
 * @returns {Promise<Object>} Configuration JSON.
 */
export async function fetchJobConfig(jobId) {
  const resp = await fetch(`http://localhost:8000/config/${jobId}`);
  if (!resp.ok) {
    throw new Error(`API error ${resp.status}`);
  }
  return resp.json();
}

/**
 * Retrieve logged training metrics for a job.
 *
 * @param {string|number} jobId - Identifier for the job.
 * @returns {Promise<Object>} Object containing metrics and summary data.
 */
export async function fetchJobMetrics(jobId) {
  const resp = await fetch(`http://localhost:8000/metrics/${jobId}`);
  if (!resp.ok) {
    throw new Error(`API error ${resp.status}`);
  }
  return resp.json();
}
