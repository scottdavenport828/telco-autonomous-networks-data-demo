import { NavLink, Route, Routes } from "react-router-dom";
import clsx from "clsx";
import Dashboard from "./pages/Dashboard";
import Incidents from "./pages/Incidents";
import IncidentDetail from "./pages/IncidentDetail";
import Workbench from "./pages/Workbench";
import Observability from "./pages/Observability";
import NetworkMap from "./pages/NetworkMap";
import Architecture from "./pages/Architecture";
import AutopilotToggle from "./components/AutopilotToggle";

const navClass = ({ isActive }: { isActive: boolean }) =>
  clsx(
    "px-3 py-2 rounded-md text-sm font-medium",
    isActive ? "bg-ink text-white" : "text-slate-700 hover:bg-slate-200",
  );

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="font-semibold text-lg text-ink">
              Telco Autonomous Networks <span className="text-slate-400 font-normal">/ Databricks-native</span>
            </div>
            <AutopilotToggle />
          </div>
          <nav className="flex gap-2">
            <NavLink to="/" end className={navClass}>
              Dashboard
            </NavLink>
            <NavLink to="/incidents" className={navClass}>
              Incidents
            </NavLink>
            <NavLink to="/workbench" className={navClass}>
              Workbench
            </NavLink>
            <NavLink to="/network" className={navClass}>
              Network
            </NavLink>
            <NavLink to="/observability" className={navClass}>
              Observability
            </NavLink>
            <NavLink to="/architecture" className={navClass}>
              Architecture
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/incidents" element={<Incidents />} />
          <Route path="/incidents/:id" element={<IncidentDetail />} />
          <Route path="/workbench" element={<Workbench />} />
          <Route path="/network" element={<NetworkMap />} />
          <Route path="/observability" element={<Observability />} />
          <Route path="/architecture" element={<Architecture />} />
        </Routes>
      </main>
    </div>
  );
}
