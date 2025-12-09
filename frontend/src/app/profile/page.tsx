"use client";

import { useAuth } from "@/contexts/AuthContext";
import { apiClient } from "@/lib/api/client";
import { getFriendlyErrorMessage } from "@/lib/utils/error";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

type AlertState = { type: "success" | "error"; message: string } | null;

export default function ProfilePage() {
  const { user, loading, logout, updateProfile, refreshUser, deleteAccount } = useAuth();
  const router = useRouter();

  const [fullName, setFullName] = useState("");
  const [profileStatus, setProfileStatus] = useState<AlertState>(null);
  const [passwordStatus, setPasswordStatus] = useState<AlertState>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteStatus, setDeleteStatus] = useState<AlertState>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [loading, user, router]);

  useEffect(() => {
    if (user?.full_name) {
      setFullName(user.full_name);
    } else {
      setFullName("");
    }
  }, [user]);

  const memberSince = useMemo(() => {
    if (!user?.created_at) return "";
    const parsed = new Date(user.created_at);
    return parsed.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }, [user?.created_at]);

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileStatus(null);

    if (!fullName.trim()) {
      setProfileStatus({ type: "error", message: "Full name cannot be empty" });
      return;
    }

    try {
      setProfileLoading(true);
      await updateProfile(fullName.trim());
      await refreshUser();
      setProfileStatus({ type: "success", message: "Profile updated successfully" });
    } catch (error) {
      setProfileStatus({
        type: "error",
        message: getFriendlyErrorMessage(error, "Unable to update profile. Please try again."),
      });
    } finally {
      setProfileLoading(false);
    }
  };

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordStatus(null);

    if (newPassword !== confirmPassword) {
      setPasswordStatus({ type: "error", message: "New password and confirmation do not match" });
      return;
    }

    if (newPassword.length < 8) {
      setPasswordStatus({ type: "error", message: "New password must be at least 8 characters" });
      return;
    }

    try {
      setPasswordLoading(true);
      await apiClient.auth.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordStatus({ type: "success", message: "Password updated successfully" });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (error) {
      setPasswordStatus({
        type: "error",
        message: getFriendlyErrorMessage(error, "Unable to change password. Please try again."),
      });
    } finally {
      setPasswordLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    setDeleteStatus(null);
    const confirmed = window.confirm(
      "Are you sure you want to delete your account? This action cannot be undone.",
    );
    if (!confirmed) return;

    try {
      setDeleteLoading(true);
      await deleteAccount();
      setDeleteStatus({ type: "success", message: "Account deleted. Redirecting..." });
      router.push("/login");
    } catch (error) {
      setDeleteStatus({
        type: "error",
        message: getFriendlyErrorMessage(error, "Failed to delete account. Please try again."),
      });
    } finally {
      setDeleteLoading(false);
    }
  };

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-indigo-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.2em] text-indigo-500 font-semibold">
              Profile
            </p>
            <h1 className="text-4xl text-display font-ultra-bold text-gray-900 tracking-tight mt-1">
              Account settings
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard"
              className="px-4 py-2 text-sm font-bold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 tracking-wide"
            >
              Back to dashboard
            </Link>
            <button
              onClick={logout}
              className="px-4 py-2 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 tracking-wide"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <section className="lg:col-span-1 bg-white shadow rounded-xl p-6 border border-indigo-50">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-ultra-bold text-xl">
                {user.full_name?.charAt(0)?.toUpperCase() || user.email.charAt(0).toUpperCase()}
              </div>
              <div>
                <p className="text-sm text-gray-500">Signed in as</p>
                <p className="text-lg font-bold text-gray-900">{user.email}</p>
              </div>
            </div>
            <dl className="mt-6 space-y-3 text-sm text-gray-600">
              <div className="flex items-center justify-between border-b border-gray-100 pb-3">
                <dt className="font-semibold text-gray-800">Full name</dt>
                <dd>{user.full_name || "Not set"}</dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="font-semibold text-gray-800">Member since</dt>
                <dd>{memberSince}</dd>
              </div>
            </dl>
            <div className="mt-6 rounded-lg bg-indigo-50 p-4 text-sm text-indigo-900">
              Keep your profile up to date for personalized experience.
            </div>
          </section>

          <section className="lg:col-span-2 space-y-6">
            <div className="bg-white shadow rounded-xl p-6 border border-indigo-50">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm uppercase tracking-[0.3em] text-indigo-500 font-semibold">
                    Profile
                  </p>
                  <h2 className="text-2xl font-ultra-bold text-gray-900 tracking-tight">
                    Update your info
                  </h2>
                  <p className="text-sm text-gray-600 mt-1">
                    Change your display name and personal information.
                  </p>
                </div>
              </div>

              <form onSubmit={handleProfileSubmit} className="mt-6 space-y-4">
                {profileStatus && (
                  <div
                    className={`rounded-md p-4 text-sm ${
                      profileStatus.type === "success"
                        ? "bg-emerald-50 text-emerald-800 border border-emerald-100"
                        : "bg-red-50 text-red-800 border border-red-100"
                    }`}
                  >
                    {profileStatus.message}
                  </div>
                )}

                <div className="grid grid-cols-1 gap-4">
                  <label className="text-sm font-semibold text-gray-800">
                    Full name
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      className="mt-2 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                      placeholder="Your name"
                    />
                  </label>
                </div>

                <div className="flex justify-end">
                  <button
                    type="submit"
                    disabled={profileLoading}
                    className="px-4 py-2 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 tracking-wide disabled:bg-indigo-400"
                  >
                    {profileLoading ? "Saving..." : "Save changes"}
                  </button>
                </div>
              </form>
            </div>

            <div className="bg-white shadow rounded-xl p-6 border border-indigo-50">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm uppercase tracking-[0.3em] text-indigo-500 font-semibold">
                    Security
                  </p>
                  <h2 className="text-2xl font-ultra-bold text-gray-900 tracking-tight">
                    Change password
                  </h2>
                  <p className="text-sm text-gray-600 mt-1">
                    Choose a strong password with at least 8 characters.
                  </p>
                </div>
              </div>

              <form onSubmit={handlePasswordSubmit} className="mt-6 space-y-4">
                {passwordStatus && (
                  <div
                    className={`rounded-md p-4 text-sm ${
                      passwordStatus.type === "success"
                        ? "bg-emerald-50 text-emerald-800 border border-emerald-100"
                        : "bg-red-50 text-red-800 border border-red-100"
                    }`}
                  >
                    {passwordStatus.message}
                  </div>
                )}

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <label className="text-sm font-semibold text-gray-800">
                    Current password
                    <input
                      type="password"
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      required
                      className="mt-2 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                    />
                  </label>
                  <label className="text-sm font-semibold text-gray-800">
                    New password
                    <input
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      required
                      minLength={8}
                      className="mt-2 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                    />
                  </label>
                  <label className="text-sm font-semibold text-gray-800 md:col-span-2">
                    Confirm new password
                    <input
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      required
                      minLength={8}
                      className="mt-2 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                    />
                  </label>
                </div>

                <div className="flex justify-end">
                  <button
                    type="submit"
                    disabled={passwordLoading}
                    className="px-4 py-2 text-sm font-bold text-white bg-gray-900 hover:bg-gray-800 rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-900 tracking-wide disabled:bg-gray-500"
                  >
                    {passwordLoading ? "Updating..." : "Update password"}
                  </button>
                </div>
              </form>
            </div>

            <div className="bg-white shadow rounded-xl p-6 border border-red-100">
              <form onSubmit={handleDeleteAccount} className="mt-6 space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm uppercase tracking-[0.3em] text-red-500 font-semibold">
                      Danger
                    </p>
                    <h2 className="text-2xl font-ultra-bold text-gray-900 tracking-tight">
                      Delete account
                    </h2>
                    <p className="text-sm text-gray-600 mt-1">
                      Permanently remove your account and all associated data. This action cannot be
                      undone.
                    </p>
                  </div>
                </div>

                {deleteStatus && (
                  <div
                    className={`mt-4 rounded-md p-4 text-sm ${
                      deleteStatus.type === "success"
                        ? "bg-emerald-50 text-emerald-800 border border-emerald-100"
                        : "bg-red-50 text-red-800 border border-red-100"
                    }`}
                  >
                    {deleteStatus.message}
                  </div>
                )}

                <div className="mt-6 flex items-center justify-between">
                  <p className="text-sm text-gray-700">
                    This will sign you out and permanently delete your data.
                  </p>
                  <button
                    onClick={handleDeleteAccount}
                    disabled={deleteLoading}
                    className="px-4 py-2 text-sm font-bold text-white bg-red-600 hover:bg-red-700 rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-70"
                  >
                    {deleteLoading ? "Deleting..." : "Delete account"}
                  </button>
                </div>
              </form>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
