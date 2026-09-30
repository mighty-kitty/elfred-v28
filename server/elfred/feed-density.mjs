export const FEED_DENSITY={
 quiet:{candidates:30,dailyMax:12,perCheck:12,intervalHours:24},
 standard:{candidates:80,dailyMax:36,perCheck:12,intervalHours:8},
 rich:{candidates:150,dailyMax:60,perCheck:15,intervalHours:4}
};
export function feedDensity(settings,system){
 const saved=settings?.data?.feed_density||{},mode=saved.agents?.[system]||saved.global||'standard';
 return {mode,...(FEED_DENSITY[mode]||FEED_DENSITY.standard)};
}
