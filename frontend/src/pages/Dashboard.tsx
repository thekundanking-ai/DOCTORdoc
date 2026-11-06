import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function Dashboard() {
  const { user, logout } = useAuth();

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold">DoctorDoc</h1>
      <p className="mt-2">
        Signed in as {user?.email} ({user?.role})
      </p>
      <Link to="/patients" className="inline-block mt-4 bg-blue-600 text-white rounded px-4 py-2">
        Patients
      </Link>
      <button onClick={() => void logout()} className="mt-4 ml-2 bg-gray-800 text-white rounded px-4 py-2">
        Log out
      </button>
    </div>
  );
}
