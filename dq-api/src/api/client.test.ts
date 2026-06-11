import { describe, it, expect, vi } from "vitest";
import { api } from "./client";
import * as token from "../auth/token";

describe("api client", () => {
  it("attaches Authorization header from token", async () => {
    const spy = vi.spyOn(token, "getToken").mockReturnValue("tok-123");
    const handlers = (api.interceptors.request as any).handlers || [];
    expect(handlers.length).toBeGreaterThan(0);
    const interceptor = handlers[0].fulfilled as (cfg: any) => any;
    const cfg = await interceptor({ headers: {} });
    expect(cfg.headers.Authorization).toBe("Bearer tok-123");
    spy.mockRestore();
  });
});
