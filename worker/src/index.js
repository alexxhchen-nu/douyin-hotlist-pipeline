/**
 * 抖音视频下载 Worker
 * POST / {url, key, referer, ua} → fetch(url) → R2.put(key, body)
 */
export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("POST only", { status: 405 });
    }

    const { url, key, referer = "https://www.douyin.com/", ua } = await request.json();

    if (!url || !key) {
      return Response.json({ error: "url and key required" }, { status: 400 });
    }

    try {
      const resp = await fetch(url, {
        headers: {
          "User-Agent": ua || "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/147.0.0.0 Safari/537.36",
          "Referer": referer,
        },
      });

      if (!resp.ok) {
        return Response.json({ error: `fetch failed: ${resp.status}`, key }, { status: 502 });
      }

      const size = parseInt(resp.headers.get("Content-Length") || "0", 10);
      await env.R2.put(key, resp.body, {
        httpMetadata: { contentType: "video/mp4" },
      });

      return Response.json({ ok: true, key, size });
    } catch (e) {
      return Response.json({ error: e.message, key }, { status: 500 });
    }
  },
};
