import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "FinSight | Risk Intelligence", description: "Real-time fraud decision narratives." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
