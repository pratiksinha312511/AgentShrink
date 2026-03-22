export default function SettingsPage() {
  return (
    <div className="card" style={{ padding: 24, maxWidth: 900 }}>
      <h1 style={{ fontSize: 22, fontWeight: 500, marginBottom: 8 }}>Settings</h1>
      <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
        Configure model, thresholds, and local runtime settings from this page.
      </p>
    </div>
  )
}
