import type { Metadata } from "next";
import { ResearchStarter } from "@/components/learning/ResearchStarter";
export const metadata: Metadata = { title: "Start research", description: "Explore a research direction, understand its methods and find a practical first step." };
export default function Page() { return <ResearchStarter />; }
