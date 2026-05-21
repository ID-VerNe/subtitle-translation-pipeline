export default function Navigation() {
  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 h-12 flex items-center justify-center nav-glass"
    >
      <div
        className="flex items-center justify-between w-full px-6"
        style={{ maxWidth: '980px' }}
      >
        <div
          className="text-white font-semibold"
          style={{
            fontSize: '14px',
            lineHeight: '1.43',
            letterSpacing: '-0.224px',
            fontWeight: 600
          }}
        >
          Subtitle Translator
        </div>
        <div
          className="text-white/60"
          style={{
            fontSize: '12px',
            lineHeight: '1.33',
            letterSpacing: '-0.12px'
          }}
        >
          v1.0.0
        </div>
      </div>
    </nav>
  );
}
