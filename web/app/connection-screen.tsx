type ConnectionScreenProps = {
  error: string | null;
  apiBase: string;
  onRetry: () => void;
};

export function ConnectionScreen({ error, apiBase, onRetry }: ConnectionScreenProps) {
  return (
    <main className="game-shell loading-screen">
      <div className="loading-card" role={error ? "alert" : "status"}>
        <span className="brand-mark">SA</span>
        <h1>{error ? "The engine is quiet" : "Waking the watchtower…"}</h1>
        <p>{error || `Waiting for the authoritative game engine at ${apiBase}.`}</p>
        {error && <button className="new-button" onClick={onRetry}>Try again</button>}
      </div>
    </main>
  );
}
