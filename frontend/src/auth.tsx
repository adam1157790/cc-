// 登录态上下文：启动时用 token 拉取用户信息
import { createContext, useContext, useEffect, useState } from "react";
import { api, probeApiBase, setApiBase } from "./api";
import type { UserInfo } from "./api";

interface AuthState {
  user: UserInfo | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  refresh: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    if (!localStorage.getItem("token")) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await api.get<UserInfo>("/api/auth/me"));
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem("token");
    setUser(null);
    location.href = "/login";
  };

  useEffect(() => {
    // 启动时探测可用 API 地址（隧道地址变更后自愈），再拉取后端下发的配置与用户信息
    (async () => {
      await probeApiBase();
      api.get<{ api_base: string }>("/api/config").then((c) => {
        if (c.api_base) setApiBase(c.api_base);
      }).catch(() => {});
      await refresh();
    })();
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
