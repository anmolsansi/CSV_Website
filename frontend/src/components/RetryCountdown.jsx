import { formatCountdown } from '../utils/retryCountdown'

// Time remaining is based on a deadline rather than decrementing on each tick,
// so background tabs and React rerenders cannot drift or reset the countdown.
export default function RetryCountdown({ seconds, label }) {
  return (
    <p className="retry-countdown" role="timer" data-testid="retry-countdown">
      <span>{label}</span>{' '}
      <strong className="retry-countdown-value">{formatCountdown(seconds)}</strong>
    </p>
  )
}
