import { useEffect, useState } from 'react'
import PropTypes from 'prop-types'
import { useNavigate } from 'react-router-dom'
import { fetchJobs } from '../api.js'
export default function JobTable() {
  const navigate = useNavigate()
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sortConfig, setSortConfig] = useState({ key: 'start_time', direction: 'asc' })

  const loadJobs = async () => {
    try {
      const data = await fetchJobs()
      setJobs(data)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadJobs()
    const id = setInterval(loadJobs, 15000)
    return () => clearInterval(id)
  }, [])

  const handleSort = (key) => {
    setSortConfig((config) => {
      if (config.key === key) {
        return { key, direction: config.direction === 'asc' ? 'desc' : 'asc' }
      }
      return { key, direction: 'asc' }
    })
  }

  if (loading) {
    return <div>Loading...</div>
  }

  if (error) {
    return <div className="text-red-500">Error: {error}</div>
  }

  const sortedJobs = [...jobs].sort((a, b) => {
    const aVal = a[sortConfig.key]
    const bVal = b[sortConfig.key]
    if (aVal === bVal) return 0
    if (sortConfig.direction === 'asc') {
      return aVal > bVal ? 1 : -1
    }
    return aVal < bVal ? 1 : -1
  })

  return (
    <table className="table-auto w-full border-collapse">
      <thead>
        <tr>
          <th className="border px-2 py-1 cursor-pointer" onClick={() => handleSort('id')}>
            Job ID{sortConfig.key === 'id' ? (sortConfig.direction === 'asc' ? ' ▲' : ' ▼') : ''}
          </th>
          <th className="border px-2 py-1 cursor-pointer" onClick={() => handleSort('status')}>
            Status{sortConfig.key === 'status' ? (sortConfig.direction === 'asc' ? ' ▲' : ' ▼') : ''}
          </th>
          <th className="border px-2 py-1 cursor-pointer" onClick={() => handleSort('start_time')}>
            Start Time{sortConfig.key === 'start_time' ? (sortConfig.direction === 'asc' ? ' ▲' : ' ▼') : ''}
          </th>
          <th className="border px-2 py-1 cursor-pointer" onClick={() => handleSort('final_val_acc')}>
            Final Val Acc{sortConfig.key === 'final_val_acc' ? (sortConfig.direction === 'asc' ? ' ▲' : ' ▼') : ''}
          </th>
        </tr>
      </thead>
      <tbody>
        {sortedJobs.map((job) => (
          <tr
            key={job.id}
            onClick={() => navigate(`/job/${job.id}`)}
            className="hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer"
          >
            <td className="border px-2 py-1">{job.id}</td>
            <td className="border px-2 py-1">{job.status}</td>
            <td className="border px-2 py-1">{job.start_time}</td>
            <td className="border px-2 py-1">{job.final_val_acc}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

JobTable.propTypes = {}
