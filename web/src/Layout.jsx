import Sidebar from "./Sidebar.jsx";

export default function Layout({ user, view, onViewChange, onLogout, children }) {
  return (
    <div className="flex min-h-screen flex-col bg-page dark:bg-page-dark sm:flex-row">
      <Sidebar user={user} view={view} onViewChange={onViewChange} onLogout={onLogout} />
      <main className="mx-auto w-full min-w-0 max-w-6xl flex-1 px-6 py-6">
        <div className="flex flex-col gap-6">{children}</div>
      </main>
    </div>
  );
}
