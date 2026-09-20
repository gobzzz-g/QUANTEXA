import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export function Layout() {
  return (
    <div className="min-h-screen bg-background text-text-main font-sans flex flex-col">
      <Sidebar />
      <main className="flex-1 p-6 overflow-x-hidden w-full max-w-[1800px] mx-auto animate-fade-in">
        <Outlet />
      </main>
    </div>
  );
}
