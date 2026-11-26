import type { MetadataRoute } from "next";
import { APP_URL } from "@/lib/site";

// Only the public pages are for search engines and AI answer engines; every
// practice page is private to its user and redirects to sign-in anyway.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/how-it-works", "/privacy"],
        disallow: [
          "/api/",
          "/admin",
          "/go/",
          "/sign-in",
          "/sign-up",
          "/onboarding",
          "/dashboard",
          "/trade",
          "/portfolio",
          "/orders",
          "/performance",
          "/costs",
          "/broker",
          "/account",
          "/plus",
        ],
      },
    ],
    sitemap: `${APP_URL}/sitemap.xml`,
    host: APP_URL,
  };
}
