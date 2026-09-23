import ApplicationPeople from './ApplicationPeople'
import ApplicationInterviews from './ApplicationInterviews'

export default function ApplicationWorkspace({ application }) {
  return (
    <div data-testid="application-f8-workspace">
      <ApplicationPeople application={application} />
      <ApplicationInterviews application={application} />
    </div>
  )
}
