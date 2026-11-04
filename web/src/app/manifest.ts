import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "CloutHook",
    short_name: "CloutHook",
    description: "Find the moment. Land the hook.",
    start_url: "/",
    display: "standalone",
    background_color: "#07060c",
    theme_color: "#07060c",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icon-512-maskable.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
