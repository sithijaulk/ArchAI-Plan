import { AdminProjectForm } from '@/components/admin/AdminProjectForm'

export default function NewProjectPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Create Gallery Project</h1>
        <p className="text-muted-foreground mt-1">Add a new project to the research gallery.</p>
      </div>
      <AdminProjectForm />
    </div>
  )
}
