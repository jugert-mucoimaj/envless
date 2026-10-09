import type { Metadata } from "next";
import { Martian_Mono, Schibsted_Grotesk } from "next/font/google";
import "./globals.css";

/*
  Two families, clearly distinct. Martian Mono carries everything that is
  literally a machine-readable name or value - keys, values, versions - and,
  set wide, the environment's name across the band. Schibsted Grotesk is for
  the sentences and the controls around them.
*/

const mono = Martian_Mono({
  variable: "--font-mono-src",
  subsets: ["latin"],
  weight: "variable",
  axes: ["wdth"],
});

const grotesk = Schibsted_Grotesk({
  variable: "--font-sans-src",
  subsets: ["latin"],
  weight: "variable",
});

export const metadata: Metadata = {
  title: "envless",
  description: "Hold every environment variable in one place, and hand it to whatever is running.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${mono.variable} ${grotesk.variable} h-full`}>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
