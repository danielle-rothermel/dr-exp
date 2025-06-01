import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { fetchJobConfig } from '../api.js'

export default function JobDetailView() {
  const { jobId } = useParams()
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
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
    </div>
  )
}
