import type { MetadataRoute } from "next";
import { APP_URL } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${APP_URL}/`, changeFrequency: "daily", priority: 1 },
    { url: `${APP_URL}/how-it-works`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${APP_URL}/privacy`, changeFrequency: "yearly", priority: 0.2 },
  ];
}
