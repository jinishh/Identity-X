import { Link } from 'react-router'
import { Button, EmptyState } from '@/components/ui'

export function NotFound() {
  return <EmptyState title="Page not found" body="The link may be wrong or the page has moved." action={<Link to="/"><Button variant="secondary">Go to dashboard</Button></Link>} />
}
