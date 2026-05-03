import type { Metadata } from "next";
import "./globals.css";

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "UniFi Threatflow Hub for AmSpec";

export const metadata: Metadata = {
  title: APP_NAME,
  description: "Centralized UniFi flow + threat dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
