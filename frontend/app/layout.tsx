import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Noto_Serif_Bengali } from "next/font/google";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const mono = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"] });
const bengali = Noto_Serif_Bengali({ variable: "--font-bengali-serif", subsets: ["bengali"], weight: ["400", "600", "700"] });

const DESCRIPTION = "Finds the safe moments to pause a Bengali drama for an ad, picks the right advertiser for each, and never places a brand next to a topic it forbids.";

export const metadata: Metadata = {
  title: "Birati · Contextual Ad Breaks",
  description: DESCRIPTION,
  applicationName: "Birati",
  openGraph: { title: "Birati · Contextual Ad Breaks", description: DESCRIPTION, type: "website" },
  twitter: { card: "summary", title: "Birati · Contextual Ad Breaks", description: DESCRIPTION },
};

export const viewport: Viewport = { themeColor: "#05060b" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable} ${bengali.variable} h-full`}>
      <body className="min-h-full">
        <div className="aurora" aria-hidden>
          <span className="animate-float-a" style={{ width: "60vw", height: "60vw", left: "-18vw", top: "-26vw", ["--c" as string]: "#ff4d8d" }} />
          <span className="animate-float-b" style={{ width: "54vw", height: "54vw", right: "-18vw", top: "-14vw", ["--c" as string]: "#8b5cf6" }} />
          <span className="animate-float-c" style={{ width: "46vw", height: "46vw", left: "26vw", top: "34vh", opacity: 0.2, ["--c" as string]: "#ff9a62" }} />
        </div>
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  );
}
