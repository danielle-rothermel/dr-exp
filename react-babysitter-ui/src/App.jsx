import JobTable from './components/JobTable.jsx'
import './App.css'

export default function App() {
  const jobs = [
    {
      id: 'job-1',
      status: 'running',
      start_time: '2024-01-01T12:00:00Z',
      final_val_acc: 0.85,
    },
    {
      id: 'job-2',
      status: 'completed',
      start_time: '2024-01-02T09:30:00Z',
      final_val_acc: 0.92,
    },
    {
      id: 'job-3',
      status: 'failed',
      start_time: '2024-01-03T15:45:00Z',
      final_val_acc: 0.4,
    },
  ]

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Babysitter UI - Job Table</h1>
      <JobTable jobs={jobs} />
    </div>
  )
}
