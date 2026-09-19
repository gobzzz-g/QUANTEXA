import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
// import { CommandPalette } from './CommandPalette';

export function Layout() {
  return (
    <div className="flex min-h-screen bg-background text-text-main font-sans">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />
        <main className="flex-1 p-6 overflow-x-hidden max-w-[1600px] w-full mx-auto">
          <Outlet />
        </main>
      </div>
      {/* <CommandPalette /> */}
    </div>
  );
}
