"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api/client";
import type { UserResponse } from "@/lib/types/api";

interface AuthContextType {
  user: UserResponse | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  updateProfile: (fullName: string) => Promise<void>;
  deleteAccount: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  // Load user on mount
  useEffect(() => {
    loadUser();
  }, []);

  const loadUser = async () => {
    try {
      const token = apiClient.getAccessToken();
      if (token) {
        const userData = await apiClient.auth.me();
        setUser(userData);
      }
    } catch {
      // Token might be expired, clear it
      apiClient.setAccessToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const login = async (email: string, password: string) => {
    try {
      await apiClient.auth.login({ email, password });
      await loadUser();
      router.push("/dashboard");
    } catch (error) {
      console.error("Login error:", error);
      throw error;
    }
  };

  const register = async (email: string, password: string, fullName?: string) => {
    try {
      await apiClient.auth.register({ email, password, full_name: fullName });
      // Auto-login after registration
      await login(email, password);
    } catch (error) {
      console.error("Registration error:", error);
      throw error;
    }
  };

  const logout = () => {
    apiClient.auth.logout();
    setUser(null);
    router.push("/login");
  };

  const refreshUser = async () => {
    await loadUser();
  };

  const updateProfile = async (fullName: string) => {
    const updatedUser = await apiClient.auth.updateProfile({ full_name: fullName });
    setUser(updatedUser);
  };

  const deleteAccount = async () => {
    await apiClient.auth.deleteAccount();
    logout();
  };

  const value: AuthContextType = {
    user,
    loading,
    login,
    register,
    logout,
    refreshUser,
    updateProfile,
    deleteAccount,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
