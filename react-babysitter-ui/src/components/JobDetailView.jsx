import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { fetchJobConfig, fetchJobMetrics } from '../api.js'

/**
 * Shows the configuration and training metrics for a single job.
 *
 * The job identifier is read from the route parameters via {@link useParams}.
 * Configuration and metrics are fetched from the API and displayed in a simple
 * read-only view.
 *
 * @component
 * @example
 * ```jsx
 * <Route path="/job/:jobId" element={<JobDetailView />} />
 * ```
 */
export default function JobDetailView() {
  const { jobId } = useParams()
  // Raw configuration for the experiment
  const [config, setConfig] = useState(null)
  // Loading state for the configuration request
  const [loading, setLoading] = useState(true)
  // Error message when fetching configuration fails
  const [error, setError] = useState(null)
  // Metrics data and summary returned from the API
  const [metrics, setMetrics] = useState(null)
  // Loading state for the metrics request
  const [metricsLoading, setMetricsLoading] = useState(true)
  // Error message when fetching metrics fails
  const [metricsError, setMetricsError] = useState(null)

  /**
   * Derive a summary of metrics from a full metrics list.
   *
   * @param {Array<Object>} list - Raw metric entries ordered by epoch.
   * @returns {Object | null} Aggregate summary or `null` when the list is empty.
   */
  const computeSummary = (list) => {
    if (!list || list.length === 0) return null
    const last = list[list.length - 1]
    return {
      final_train_loss: last.train_loss,
      final_val_acc: last.val_acc,
      num_epochs: last.epoch,
    }
  }

  useEffect(() => {
    /**
     * Fetch the job configuration from the API.
     */
    const loadConfig = async () => {
      setLoading(true)
      try {
        const data = await fetchJobConfig(jobId)
        setConfig(data.config)
        setError(null)
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    loadConfig()
  }, [jobId])

  useEffect(() => {
    /**
     * Fetch metrics and derive a summary for display.
     */
    const loadMetrics = async () => {
      setMetricsLoading(true)
      try {
        const data = await fetchJobMetrics(jobId)
        setMetrics({
          metrics: data.metrics,
          summary: data.summary || computeSummary(data.metrics),
        })
        setMetricsError(null)
      } catch (e) {
        setMetricsError(e.message)
      } finally {
        setMetricsLoading(false)
      }
    }
    loadMetrics()
  }, [jobId])

  if (loading) {
    return <div>Loading...</div>
  }
  if (error) {
    return <div className="text-red-500">Error: {error}</div>
  }

  return (
    <div>
      <Link to="/" className="text-blue-500 underline">Back to Jobs</Link>
      <h2 className="text-xl font-semibold mt-2 mb-2">Job {jobId} Configuration</h2>
      <pre className="bg-slate-100 dark:bg-slate-800 p-4 rounded overflow-auto">
        {JSON.stringify(config, null, 2)}
      </pre>
      <h2 className="text-xl font-semibold mt-4 mb-2">Metrics Summary</h2>
      {metricsLoading ? (
        <div>Loading metrics...</div>
      ) : metricsError ? (
        <div className="text-red-500">Error: {metricsError}</div>
      ) : metrics && metrics.summary ? (
        <pre className="bg-slate-100 dark:bg-slate-800 p-4 rounded overflow-auto">
          {Object.entries(metrics.summary)
            .map(([k, v]) => `${k}: ${v}`)
            .join('\n')}
        </pre>
      ) : (
        <div>No metrics available.</div>
      )}

      <h2 className="text-xl font-semibold mt-4 mb-2">Logs</h2>
      {metricsLoading ? (
        <div>Loading logs...</div>
      ) : metricsError ? (
        <div className="text-red-500">Error: {metricsError}</div>
      ) : metrics && metrics.metrics ? (
        <pre className="bg-slate-100 dark:bg-slate-800 p-4 rounded overflow-auto h-60 whitespace-pre-wrap">
          {metrics.metrics.map((m) => JSON.stringify(m)).join('\n')}
        </pre>
      ) : (
        <div>No logs available.</div>
      )}
    </div>
  )
}
