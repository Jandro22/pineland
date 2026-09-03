# Pineland COIN-SIM Research Bibliography v0.1

**Coverage:** Research explicitly used or invoked in the conceptual design and implementation of Pineland COIN-SIM through release `v0.7.0` and planning for Phase 8.

**Purpose:** Maintain a canonical research record for later citation, parameterization, model validation, literature review, and eventual publication.

**Important:** Inclusion means the source influenced the design, motivated a mechanism, supplied empirical evidence, or provided a modeling methodology. It does **not** mean that every numerical parameter in Pineland is directly estimated from that source.

## Status categories

**CORE**: Directly influenced model architecture, equations, state variables, or major assumptions.

**SUPPORT**: Used to evaluate, justify, complicate, or validate a modeled mechanism.

**METHOD**: Modeling, calibration, sensitivity, visualization, or data methodology.

**REPORT/DATA**: Research report, dataset, codebook, or major non-journal source.

---

# I. Agent-Based Modeling, Mobilization, Networks, and Emergence

### 1. Epstein, Joshua M. 2002. [CORE]

“Modeling Civil Violence: An Agent-Based Computational Approach.” *Proceedings of the National Academy of Sciences* 99(Suppl. 3): 7243-7250.

DOI: 10.1073/pnas.092080199

**Pineland use:** Foundational civil-violence ABM; grievance, legitimacy, perceived risk, activation thresholds, state presence, and agent-level mobilization.

---

### 2. Bennett, D. Scott. 2008. [CORE]

“Governments, Civilians, and the Evolution of Insurgency: Modeling the Early Dynamics of Insurgencies.” *Journal of Artificial Societies and Social Simulation* 11(4): 7.

**Pineland use:** Government-civilian-insurgent feedback, fear, anger/grievance updates, civilian harm, repeated-run analysis, and insurgency emergence.

---

### 3. Cioffi-Revilla, Claudio, and Mark Rouleau. 2010. [CORE]

“MASON RebeLand: An Agent-Based Model of Politics, Environment, and Insurgency.” *International Studies Review* 12(1): 31-52.

DOI: 10.1111/j.1468-2486.2009.00911.x

**Pineland use:** Explicit political, social, environmental, and geographic state rather than a purely battlefield simulation.

---

### 4. Granovetter, Mark. 1978. [CORE]

“Threshold Models of Collective Behavior.” *American Journal of Sociology* 83(6): 1420-1443.

DOI: 10.1086/226707

**Pineland use:** Individual mobilization thresholds and collective cascades.

---

### 5. Watts, Duncan J. 2002. [CORE]

“A Simple Model of Global Cascades on Random Networks.” *Proceedings of the National Academy of Sciences* 99(9): 5766-5771.

DOI: 10.1073/pnas.082090499

**Pineland use:** Network cascades, systemic susceptibility, and propagation across heterogeneous communities.

---

### 6. Centola, Damon, and Michael Macy. 2007. [CORE]

“Complex Contagions and the Weakness of Long Ties.” *American Journal of Sociology* 113(3): 702-734.

DOI: 10.1086/521848

**Pineland use:** Reinforcement-dependent political mobilization rather than assuming simple epidemic contagion.

---

### 7. Centola, Damon. 2010. [CORE]

“The Spread of Behavior in an Online Social Network Experiment.” *Science* 329(5996): 1194-1197.

DOI: 10.1126/science.1185231

**Pineland use:** Empirical support for complex social contagion and redundant reinforcement.

---

### 8. Schweitzer, Frank, and Georges Andres. 2022. [SUPPORT]

“Social Nucleation: Group Formation as a Phase Transition.” *Physical Review E* 105: 044301.

DOI: 10.1103/PhysRevE.105.044301

**Pineland use:** Organizational nucleation and the transition from social clusters to persistent organizations.

---

### 9. Su, Zhen, Wei Wang, Lixiang Li, Jinghua Xiao, H. Eugene Stanley, et al. 2017. [SUPPORT]

“Emergence of Hysteresis Loop in Social Contagions on Complex Networks.” *Scientific Reports* 7: 6103.

DOI: 10.1038/s41598-017-06286-w

**Pineland use:** Hysteresis, path dependence, and why political systems may not return to their original state when an initiating shock disappears.

---

### 10. Füllsack, Manfred, Simon Plakolb, and Georg Jäger. 2021. [SUPPORT]

“Predicting Regime Shifts in Social Systems Modelled with Agent-Based Methods.” *Journal of Computational Social Science* 4: 163-185.

DOI: 10.1007/s42001-020-00071-y

**Pineland use:** Critical transitions and regime-shift diagnostics in ABMs.

---

### 11. Helfmann, Luzie, Jan Heitzig, Péter Koltai, et al. 2021. [SUPPORT]

“Statistical Analysis of Tipping Pathways in Agent-Based Models.” *European Physical Journal Special Topics* 230: 3249-3271.

DOI: 10.1140/epjs/s11734-021-00191-0

**Pineland use:** Transition pathways, reduced dynamics, metastability, and tipping analysis.

---

# II. Civilian Control, Collaboration, Legitimacy, and Rebel Governance

### 12. Condra, Luke N., and Jacob N. Shapiro. 2012. [CORE]

“Who Takes the Blame? The Strategic Effects of Collateral Damage.” *American Journal of Political Science* 56(1): 167-187.

DOI: 10.1111/j.1540-5907.2011.00542.x

**Pineland use:** Civilian harm, attribution, grievance, and spatially mediated political consequences.

---

### 13. Berman, Eli, Jacob N. Shapiro, and Joseph H. Felter. 2011. [CORE]

“Can Hearts and Minds Be Bought? The Economics of Counterinsurgency in Iraq.” *Journal of Political Economy* 119(4): 766-819.

DOI: 10.1086/661983

**Pineland use:** Service provision, insurgent violence, governance, and information/cooperation mechanisms.

---

### 14. Schutte, Sebastian. 2017. [CORE]

“Violence and Civilian Loyalties: Evidence from Afghanistan.” *Journal of Conflict Resolution* 61(8): 1595-1625.

DOI: 10.1177/0022002715626249

**Pineland use:** Spatial scale, civilian reaction to violence, loyalty, and aggregation sensitivity.

---

### 15. Rubin, Michael A. 2020. [CORE]

“Rebel Territorial Control and Civilian Collective Action in Civil War: Evidence from the Communist Insurgency in the Philippines.” *Journal of Conflict Resolution* 64(2-3): 459-489.

DOI: 10.1177/0022002719863844

**Pineland use:** Civilian collective-action capacity, social networks, rebel territorial control, and governance costs.

---

### 16. Breslawski, Jori. 2021. [SUPPORT]

“The Social Terrain of Rebel Held Territory.” *Journal of Conflict Resolution* 65(2-3): 453-479.

DOI: 10.1177/0022002720951857

**Pineland use:** Variation in rebel-held political orders and community cohesion.

---

### 17. Jentzsch, Corinna, and Abbey Steele. 2023. [CORE]

“Social Control in Civil Wars.” *Civil Wars* 25: 452-471.

DOI: 10.1080/13698249.2023.2250699

**Pineland use:** Separation of territorial control from social control.

---

### 18. Condra, Luke N., and Austin L. Wright. 2019. [CORE]

“Civilians, Control, and Collaboration during Civil Conflict.” *International Studies Quarterly* 63(4): 897-907.

DOI: 10.1093/isq/sqz042

**Pineland use:** Perceived conduct of armed actors, civilian cooperation, and collaboration under varying control.

---

### 19. Wright, Austin L., Luke N. Condra, Jacob N. Shapiro, and Andrew C. Shaver. 2025. [SUPPORT]

“Civilian Harm, Wartime Informing, and Counterinsurgent Operations.” *Quarterly Journal of Political Science* 20(4): 513-535.

DOI: 10.1561/100.00024061

**Pineland use:** Civilian harm, subsequent information provision, and information-security feedback.

---

### 20. Dyrstad, Karin, and Solveig Hillesund. 2020. [CORE]

“Explaining Support for Political Violence: Grievance and Perceived Opportunity.” *Journal of Conflict Resolution* 64(9): 1724-1753.

DOI: 10.1177/0022002720909886

**Pineland use:** Separation between latent support for violence and actual participation.

---

### 21. Gohdes, Anita R., and Zachary C. Steinert-Threlkeld. 2024. [CORE]

“Civilian Behavior on Social Media during Civil War.” *American Journal of Political Science*.

DOI: 10.1111/ajps.12899

**Pineland use:** Control-contingent public political expression and the distinction between private preference and publicly displayed allegiance.

---

### 22. Stewart, Megan A., and Yu-Ming Liou. 2017. [SUPPORT]

“Do Good Borders Make Good Rebels? Territorial Control and Civilian Casualties.” *The Journal of Politics* 79: 284-301.

DOI: 10.1086/688699

**Pineland use:** Rebel territorial control, civilian relations, and domestic versus external territorial bases.

---

### 23. O’Connor, Francis. 2023. [SUPPORT]

“Clandestinity and Insurgent Consolidation: The M-19’s Rebel Governance in Urban Colombia.” *Political Geography* 105: 102930.

DOI: 10.1016/j.polgeo.2023.102930

**Pineland use:** Urban social control and rebel governance without conventional territorial domination.

---

### 24. Uribe, Andres D., and Sebastian van Baalen. 2024. [SUPPORT]

“Governing the Shadows: Territorial Control and State Making in Civil War.”

*Comparative Political Studies.*

DOI: 10.1177/00104140241290200

**Pineland use:** Rebel governance in state-dominated territory and hidden/parallel institutional systems.

---

### 25. van Baalen, Sebastian. 2021. [SUPPORT]

“Local Elites, Civil Resistance, and the Responsiveness of Rebel Governance in Côte d’Ivoire.” *Journal of Peace Research* 58(5): 930-944.

DOI: 10.1177/0022343320965675

**Pineland use:** Local elites as intermediaries, bargaining nodes, and determinants of governance responsiveness.

---

### 26. Mampilly, Zachariah, and Megan A. Stewart. 2021. [CORE]

“A Typology of Rebel Political Institutional Arrangements.” *Journal of Conflict Resolution* 65(1): 15-45.

DOI: 10.1177/0022002720935642

**Pineland use:** Rebel political institutions as heterogeneous, changing organizational systems.

---

# III. Recruitment, Participation, Organizational Structure, and Evolution

### 27. Gates, Scott. 2002. [CORE]

“Recruitment and Allegiance: The Microfoundations of Rebellion.” *Journal of Conflict Resolution* 46(1): 111-130.

DOI: 10.1177/0022002702046001007

**Pineland use:** Recruitment, geography, ideology, identity, retention, allegiance, and organizational cohesion.

---

### 28. Humphreys, Macartan, and Jeremy M. Weinstein. 2008. [CORE]

“Who Fights? The Determinants of Participation in Civil War.” *American Journal of Political Science* 52(2): 436-455.

DOI: 10.1111/j.1540-5907.2008.00322.x

**Pineland use:** Multicausal participation rather than a single grievance explanation.

---

### 29. Schaub, Max, and Daniel Auer. 2023. [CORE]

“Rebel Recruitment and Migration: Theory and Evidence From Southern Senegal.” *Journal of Conflict Resolution* 67: 1155-1182.

DOI: 10.1177/00220027221118258

**Pineland use:** Recruitment threat as a cause of migration and endogenous depletion of recruitment pools.

---

### 30. Eck, Kristine. 2014. [SUPPORT]

“Coercion in Rebel Recruitment.” *Security Studies* 23: 364-398.

DOI: 10.1080/09636412.2014.905368

**Pineland use:** Dynamic recruitment strategies, conflict pressure, coercive recruitment, and migration/defection constraints.

---

### 31. Sawyer, Katherine, and Talbot M. Andrews. 2020. [SUPPORT]

“Rebel Recruitment and Retention in Civil Conflict.” *International Interactions* 46: 872-892.

DOI: 10.1080/03050629.2020.1814765

**Pineland use:** Joining and retention as separate organizational processes.

---

### 32. Hanson, Kolby. 2020. [SUPPORT]

“Good Times and Bad Apples: Rebel Recruitment in Crackdown and Truce.” *American Journal of Political Science*.

DOI: 10.1111/ajps.12555

**Pineland use:** Recruitment quantity versus recruit quality, commitment, discipline, and organizational effectiveness.

---

### 33. Plapinger, S. 2022. [SUPPORT]

“Insurgent Recruitment Practices and Combat Effectiveness in Civil War: The Black September Conflict in Jordan.” *Security Studies* 31: 251-290.

DOI: 10.1080/09636412.2022.2072234

**Pineland use:** Recruitment quality, interpersonal trust, discipline, cohesion, and combat effectiveness.

---

### 34. Albrecht, H. 2022. [SUPPORT]

“Saints and Warriors: Strategic Choice in Rebel Recruitment in the Syrian Civil War.” *Civil Wars* 24: 387-410.

DOI: 10.1080/13698249.2022.2125722

**Pineland use:** Recruitment strategies changing over organizational lifecycles.

---

### 35. Soules, Michael J. 2023. [SUPPORT]

“Recruiting Rebels: Introducing the Rebel Appeals and Incentives Dataset.” *Journal of Conflict Resolution* 67: 1811-1837.

DOI: 10.1177/00220027231154813

**Pineland use:** Heterogeneous ideological and material recruitment appeals.

---

### 36. Soules, Michael J., and Mark Berlin. 2025. [SUPPORT]

“A Call to Arms: How Rebel Groups Choose Their Recruitment Appeals.” *Journal of Conflict Resolution*.

DOI: 10.1177/00220027251375624

**Pineland use:** Recruitment appeal breadth, ideology, organizational cohesion, and potential fractionalization.

---

### 37. Myers, Emily. 2024. [SUPPORT]

“Insurgent Conscription for Capacity and Control: State Violence and Coerced Recruitment in Civil War.” *Journal of Conflict Resolution*.

DOI: 10.1177/00220027241269952

**Pineland use:** Organizational control, state violence, and changing recruitment institutions.

---

### 38. Holtermann, Helge. 2016. [CORE]

“How Can Weak Insurgent Groups Grow? Insights From Nepal.” *Terrorism and Political Violence* 28: 316-337.

DOI: 10.1080/09546553.2014.908775

**Pineland use:** Pre-existing networks, weak-state reach, collaboration, and survival of initially weak organizations.

---

### 39. Moore, Pauline. 2019. [SUPPORT]

“When Do Ties Bind? Foreign Fighters, Social Embeddedness, and Violence against Civilians.” *Journal of Peace Research* 56: 279-294.

DOI: 10.1177/0022343318804594

**Pineland use:** Local versus foreign embeddedness, geographic/social distance, and civilian relationships.

---

### 40. Zech, Steven T., and Michael Gabbay. 2016. [CORE]

“Social Network Analysis in the Study of Terrorism and Insurgency: From Organization to Politics.” *International Studies Review* 18(2): 214-243.

DOI: 10.1093/isr/viv011

**Pineland use:** Organizational network topology, network metrics, militant-group structure, and the limits of purely organizational SNA.

---

# IV. Geography, Towns, Cities, Terrain, and Conflict Diffusion

### 41. Staniland, Paul. 2010. [CORE]

“Cities on Fire: Social Mobilization, State Policy, and Urban Insurgency.” *Comparative Political Studies* 43(12): 1623-1649.

DOI: 10.1177/0010414010374022

**Pineland use:** Cities as distinct insurgent environments, urban social mobilization, and state-policy constraints.

---

### 42. Schutte, Sebastian, and Nils B. Weidmann. 2011. [CORE]

“Diffusion Patterns of Violence in Civil Wars.” *Political Geography* 30(3): 143-152.

DOI: 10.1016/j.polgeo.2011.03.005

**Pineland use:** Spatial escalation versus relocation and geographically structured diffusion.

---

### 43. Zhukov, Yuri M. 2012. [CORE]

“Roads and the Diffusion of Insurgent Violence: The Logistics of Conflict in Russia’s North Caucasus.” *Political Geography* 31(3): 144-156.

DOI: 10.1016/j.polgeo.2011.12.002

**Pineland use:** Road connectivity, logistics, spatial propagation, and non-Euclidean geographic distance.

---

### 44. Lucas, Rebecca. 2020. [SUPPORT]

“Taking to the Streets: The Kurdistan Workers’ Party and the Urbanization of Insurgency.” *Small Wars & Insurgencies* 31: 61-86.

DOI: 10.1080/09592318.2020.1672963

**Pineland use:** Urban versus rural insurgency sustainability and pre-existing social networks.

---

### 45. Dolan, Thomas, Clayton Besaw, and Joseph R. Butler. 2018. [SUPPORT]

“Where the Insurgents Aren’t.” *Journal of Conflict Resolution* 62: 1262-1283.

DOI: 10.1177/0022002716678985

**Pineland use:** Population density, cities, rural local knowledge, and nonterritorial insurgency geography.

---

### 46. Reeder, Bryce W. 2018. [CORE]

“The Political Geography of Rebellion: Using Event Data to Identify Insurgent Territory, Preferences, and Relocation Patterns.” *International Studies Quarterly* 62(3): 696-707.

DOI: 10.1093/isq/sqy016

**Pineland use:** Organizational habitat, terrain, borders, resources, territorial preferences, and rebel relocation.

---

### 47. Uzonyi, Gary, and Ore Koren. 2024. [CORE]

“The Urban Origins of Rebellion.” *Journal of Conflict Resolution* 68: 1717-1740.

DOI: 10.1177/00220027231202038

**Pineland use:** Distinction between where armed organizations originate and where they later sustain military activity.

---

### 48. Browning, Raiha, Hamish Patten, Judith Rousseau, and Kerrie Mengersen. 2026. [METHOD / SUPPORT]

“Bayesian Spatiotemporal Modelling of Political Violence and Conflict Events Using Discrete-Time Hawkes Processes.” *Journal of the Royal Statistical Society: Series A*.

DOI: 10.1093/jrsssa/qnag039

**Pineland use:** Statistical benchmark for burstiness, temporal clustering, spatial propagation, and comparison of mechanistic ABM output against event-process models.

---

# V. Police, Militias, Local Forces, and Security Institutions

### 49. Peic, Goran. 2014. [CORE]

“Civilian Defense Forces, State Capacity, and Government Victory in Counterinsurgency Wars.” *Studies in Conflict & Terrorism* 37(2): 162-184.

DOI: 10.1080/1057610X.2014.862904

**Pineland use:** Local defense forces, state capacity, local information, and counterinsurgent outcomes.

---

### 50. Clayton, Govinda, and Andrew Thomson. 2016. [CORE]

“Civilianizing Civil Conflict: Civilian Defense Militias and the Logic of Violence in Intrastate Conflict.” *International Studies Quarterly* 60(3): 499-510.

DOI: 10.1093/isq/sqv011

**Pineland use:** Militias, civilian violence, retaliation, and delegation tradeoffs.

---

### 51. Biberman, Yelena. 2018. [CORE]

“Self-Defense Militias, Death Squads, and State Outsourcing of Violence in India and Turkey.” *Journal of Strategic Studies* 41(5): 751-781.

DOI: 10.1080/01402390.2016.1202822

**Pineland use:** State proxy selection, local knowledge, collaborator supply, control, and principal-agent tradeoffs.

---

### 52. Eck, Kristine. 2025. [CORE]

“Police Deployment in Armed Conflict: A Typology and Multi-Case Application.” *Policing and Society* 35(4): 465-486.

DOI: 10.1080/10439463.2024.2387702

**Pineland use:** Police vacuum, normal policing, expanded policing, supportive policing, counterinsurgency policing, and the police-military continuum.

---

### 53. Pankhurst, Dale. 2025. [SUPPORT]

“What Contributions Do Anti-Insurgent Militias Produce during Armed Conflict? Exploring the Capabilities of Anti-Insurgent Militias in Colombia and the Philippines.” *Journal of Strategic Studies* 48(5): 1049-1072.

DOI: 10.1080/01402390.2025.2487838

**Pineland use:** Local-force capabilities and institutional tradeoffs.

---

### 54. Saad, Mohamed. 2024. [SUPPORT]

“Localization of the Counterinsurgency in Sinai: A Case Study on Integrating Local Population into Counterinsurgency Combat Operations in Sinai.” *Digest of Middle East Studies* 33(2): 108-124.

DOI: 10.1111/dome.12320

**Pineland use:** Integration of local forces, institutional incorporation, and local political effects.

---

### 55. Raveendran, Jithin. 2026. [SUPPORT]

“Legitimacy, Power, and the Politics of Security in Localized Counterinsurgency: Lessons from India, Iraq, and Beyond.” *Small Wars & Insurgencies* 37(2): 398-424.

DOI: 10.1080/09592318.2026.2616365

**Pineland use:** Long-term sustainability of locally embedded security actors and institutional integration.

---

# VI. External Support, Intervention, Refugees, and Internationalization

### 56. Salehyan, Idean, Kristian Skrede Gleditsch, and David E. Cunningham. 2011. [CORE]

“Explaining External Support for Insurgent Groups.” *International Organization* 65(4): 709-744.

DOI: 10.1017/S0020818311000233

**Pineland use:** Principal-agent explanation of foreign sponsorship, transnational ties, rivalries, and sponsor selection.

---

### 57. Sawyer, Katherine, Kathleen Gallagher Cunningham, and William Reed. 2017. [CORE]

“The Role of External Support in Civil War Termination.” *Journal of Conflict Resolution* 61(6): 1174-1202.

DOI: 10.1177/0022002715600761

**Pineland use:** External resources, conflict duration, bargaining uncertainty, and termination.

---

### 58. Huang, Reyko, and Patricia L. Sullivan. 2021. [CORE]

“Arms for Education? External Support and Rebel Social Services.” *Journal of Peace Research* 58(4): 794-808.

DOI: 10.1177/0022343320940749

**Pineland use:** Different support types, rebel governance, services, and organizational incentives.

---

### 59. Terpstra, Niels. 2020. [CORE]

“Rebel Governance, Rebel Legitimacy, and External Intervention: Assessing Three Phases of Taliban Rule in Afghanistan.” *Small Wars & Insurgencies* 31(6): 1143-1173.

DOI: 10.1080/09592318.2020.1757916

**Pineland use:** External intervention, withdrawal, rebel legitimacy, and changing political orders.

---

### 60. Sambanis, Nicholas, Stergios Skaperdas, and William Wohlforth. 2020. [SUPPORT]

“External Intervention, Identity, and Civil War.” *Comparative Political Studies* 53(14): 2155-2182.

DOI: 10.1177/0010414020912279

**Pineland use:** Foreign intervention interacting with identity and polarization.

---

### 61. Sexton, Renard, and Christoph Zürcher. 2023/2024. [CORE]

“Aid, Attitudes, and Insurgency: Evidence from Development Projects in Northern Afghanistan.” *American Journal of Political Science*.

DOI: 10.1111/ajps.12778

**Pineland use:** Development aid, economic perceptions, government attitudes, consultation, and limits of simple “hearts and minds” assumptions.

---

### 62. Langlotz, Sarah. 2026. [CORE]

“Foreign Interventions and Community Cohesion in Times of Conflict.” *Journal of Development Economics* 182: 103751.

DOI: 10.1016/j.jdeveco.2026.103751

**Pineland use:** Foreign military presence, local community cohesion, trust, informal institutions, and possible unintended social consequences.

---

### 63. Salehyan, Idean, and Kristian Skrede Gleditsch. 2006. [CORE]

“Refugees and the Spread of Civil War.” *International Organization* 60(2): 335-366.

DOI: 10.1017/S0020818306060103

**Pineland use:** Cross-border displacement, refugee social networks, and transnational conflict diffusion. Refugees are not treated as insurgents by default.

---

# VII. Political Parties, Patronage, Rebel-to-Party Transformation, and Governance

### 64. Matanock, Aila M., and Paul Staniland. 2018. [CORE]

“How and Why Armed Groups Participate in Elections.” *Perspectives on Politics*.

**Pineland use:** Armed-electoral mixed strategies and elections as a possible political channel for organized armed actors.

---

### 65. Manning, Carrie, and Ian Smith. 2016. [CORE]

“Political Party Formation by Former Armed Opposition Groups after Civil War.” *Democratization* 23(6): 972-989.

DOI: 10.1080/13510347.2016.1159556

**Pineland use:** Transformation of armed organizations into political parties.

---

### 66. Lyons, Terrence. 2016. [SUPPORT]

“From Victorious Rebels to Strong Authoritarian Parties: Prospects for Post-War Democratization.” *Democratization* 23(6): 1026-1041.

DOI: 10.1080/13510347.2016.1168404

**Pineland use:** Organizational capital surviving conflict and becoming political-party capacity.

---

### 67. Zaks, Sherry. 2025. [CORE]

“Repurposing Rebellion: Building Rebel Successor Parties on the Heels of War?” *European Journal of International Relations* 31(2).

DOI: 10.1177/13540661251320890

**Pineland use:** Wartime organizational structures becoming proto-party institutions.

---

### 68. Uribe, Andres D. 2024. [CORE]

“Coercion, Governance, and Political Behavior in Civil War.” *Journal of Peace Research* 61(4): 529-544.

DOI: 10.1177/00223433221147939

**Pineland use:** Armed governance and subsequent electoral/political behavior.

---

### 69. Reno, William. 2007. [CORE]

“Patronage Politics and the Behavior of Armed Groups.” *Civil Wars* 9(4): 324-342.

DOI: 10.1080/13698240701699409

**Pineland use:** Patronage, political networks, rents, organizational incentives, and state/nonstate interaction.

---

### 70. Seymour, Lee J. M. 2014. [CORE]

“Why Factions Switch Sides in Civil Wars: Rivalry, Patronage, and Realignment in Sudan.” *International Security* 39(2): 92-131.

DOI: 10.1162/ISEC_a_00179

**Pineland use:** Factional alignment, side-switching, patronage, rivalry, and endogenous coalition change.

---

# VIII. Human Social Scale, Community Structure, and Mobility

### 71. Hill, R. A., and R. I. M. Dunbar. 2003. [CORE]

“Social Network Size in Humans.” *Human Nature* 14: 53-72.

DOI: 10.1007/S12110-003-1016-Y

**Pineland use:** Approximate meaningful social-network scale and the empirical basis for sparse rather than fully connected networks.

---

### 72. Dunbar, R. I. M., Valerio Arnaboldi, Marco Conti, and Andrea Passarella. 2015. [CORE]

“The Structure of Online Social Networks Mirrors Those in the Offline World.” *Social Networks* 43: 39-47.

DOI: 10.1016/j.socnet.2015.04.005

**Pineland use:** Nested social layers and approximately 5, 15, 50, and 150 relationship scales.

---

### 73. Dunbar, Robin I. M., and Richard Sosis. 2018. [CORE]

“Optimising Human Community Sizes.” *Evolution and Human Behavior* 39(1).

DOI: 10.1016/j.evolhumbehav.2017.11.001

**Pineland use:** Stable human community sizes, institutionalization, and community scaling.

---

### 74. Kordsmeyer, Tobias, Pádraig Mac Carron, and R. I. M. Dunbar. 2017. [SUPPORT]

“Sizes of Permanent Campsite Communities Reflect Constraints on Natural Human Communities.” *Current Anthropology* 58(2): 289-294.

DOI: 10.1086/690731

**Pineland use:** Empirical support for nested community sizes.

---

### 75. González, Marta C., César A. Hidalgo, and Albert-László Barabási. 2008. [CORE]

“Understanding Individual Human Mobility Patterns.” *Nature* 453: 779-782.

DOI: 10.1038/nature06958

**Pineland use:** Strong regularity and repeated return in human mobility.

---

### 76. Song, Chaoming, Tal Koren, Pu Wang, and Albert-László Barabási. 2010. [CORE]

“Modelling the Scaling Properties of Human Mobility.” *Nature Physics* 6: 818-823.

DOI: 10.1038/nphys1760

**Pineland use:** Exploration plus preferential-return mobility rather than random walks.

---

### 77. Alessandretti, Laura, Piotr Sapiezynski, Vedran Sekara, Sune Lehmann, and Andrea Baronchelli. 2018. [CORE]

“Evidence for a Conserved Quantity in Human Mobility.” *Nature Human Behaviour* 2: 485-491.

DOI: 10.1038/s41562-018-0364-x

**Pineland use:** Stable personal activity sets, with approximately 25 familiar locations as a calibration reference rather than a hard constant.

---

### 78. Simini, Filippo, Marta C. González, Amos Maritan, and Albert-László Barabási. 2012. [CORE]

“A Universal Model for Mobility and Migration Patterns.” *Nature* 484: 96-100.

DOI: 10.1038/nature10856

**Pineland use:** Radiation-model baseline for interlocality movement.

---

### 79. Cabanas-Tirapu, Oriol, Lluís Danús, Esteban Moro, Marta Sales-Pardo, Roger Guimerà, et al. 2025. [SUPPORT]

“Human Mobility Is Well Described by Closed-Form Gravity-Like Models Learned Automatically from Data.” *Nature Communications* 16: 1336.

**Pineland use:** Support for retaining interpretable gravity-type models as competitors to more complicated mobility systems.

---

# IX. Language, Interpreters, and Cross-Cultural Brokerage

### 80. de Jong, Sara. 2025. [CORE]

“Brokering War: Afghan Interpreters, Western Soldiers and Unequal Encounters in Crisis.” *Cultural Studies* 39(2): 248-268.

DOI: 10.1080/09502386.2024.2437434

**Pineland use:** Interpreters as cultural, social, political, and informational brokers rather than simple translation bonuses.

---

### 81. de Jong, Sara. 2023. [SUPPORT]

“Brokers Betrayed: The Afterlife of Afghan Interpreters Employed by Western Armies.” *Journal of International Development*.

DOI: 10.1002/jid.3696

**Pineland use:** Interpreter social position, political attribution, and long-term consequences of broker relationships.

---

# X. Model Documentation, Calibration, Sensitivity, and Visualization

### 82. Grimm, Volker, et al. 2020. [METHOD]

“The ODD Protocol for Describing Agent-Based and Other Simulation Models: A Second Update to Improve Clarity, Replication, and Structural Realism.” *Journal of Artificial Societies and Social Simulation* 23(2): 7.

DOI: 10.18564/jasss.4259

**Pineland use:** Formal model documentation and reproducibility.

---

### 83. Thiele, Jan C., Winfried Kurth, and Volker Grimm. 2014. [METHOD]

“Facilitating Parameter Estimation and Sensitivity Analysis of Agent-Based Models: A Cookbook Using NetLogo and R.” *Journal of Artificial Societies and Social Simulation* 17(3): 11.

DOI: 10.18564/jasss.2503

**Pineland use:** Parameter estimation, calibration workflow, and sensitivity analysis.

---

### 84. “A Critical Review of Common Pitfalls and Guidelines to Effectively Infer Parameters of Agent-Based Models Using Approximate Bayesian Computation.” 2024. [METHOD]

*Environmental Modelling & Software* 172: 105905.

DOI: 10.1016/j.envsoft.2023.105905

**Pineland use:** Approximate Bayesian Computation, parameter identifiability, and avoiding poorly identified ABM calibration.

**Bibliographic action:** Import author list from Crossref/publisher before final manuscript use.

---

### 85. Shneiderman, Ben. 1996. [METHOD]

“The Eyes Have It: A Task by Data Type Taxonomy for Information Visualizations.” *Proceedings of the IEEE Symposium on Visual Languages*, 336-343.

DOI: 10.1109/VL.1996.545307

**Pineland use:** “Overview first, zoom and filter, then details on demand,” forming the basis for the causal-microscope interface.

---

# XI. Non-Journal Sources Actually Used

These are not papers in the narrow sense, but they have materially influenced Pineland and should remain in the master reference database.

### 86. Kalyvas, Stathis N. 2006. [CORE / BOOK]

*The Logic of Violence in Civil War.* Cambridge University Press.

**Pineland use:** Territorial control, selective violence, collaboration, civilian information, and imperfect knowledge.

---

### 87. Kuran, Timur. 1995. [CORE / BOOK]

*Private Truths, Public Lies: The Social Consequences of Preference Falsification.*

**Pineland use:** Private preference versus public behavior, concealed political beliefs, and cascades.

---

### 88. Mao Tse-tung. [HISTORICAL THEORY]

*On Guerrilla Warfare.*

**Pineland use:** Initially considered as a possible formal organizing framework; later deliberately demoted to a historical theory that the model may reproduce or reject rather than hard-code.

---

### 89. Galula, David. [HISTORICAL THEORY]

*Counterinsurgency Warfare: Theory and Practice.*

**Pineland use:** Background COIN theory, not a primary formal model.

---

# XII. RAND Research Reports Used

### 90. Connable, Ben, and Martin C. Libicki. 2010. [REPORT]

*How Insurgencies End.* RAND Corporation, MG-965.

**Pineland use:** Conflict outcomes, insurgency termination, external support, sanctuary, and historical case patterns.

---

### 91. Pirnie, Bruce R., and Edward O’Connell. 2008. [REPORT]

*Counterinsurgency in Iraq (2003-2006).* RAND Corporation, MG-595.3.

**Pineland use:** Small-scale engagements, tactical consequences, and the relationship between tactical actions and political outcomes.

---

### 92. Perry, Walter L., and John Gordon IV. 2008. [REPORT]

*Analytic Support to Intelligence in Counterinsurgencies.* RAND Corporation, MG-682-OSD.

**Pineland use:** Intelligence under insurgency, uncertain enemy structure, analytical support, information requirements by conflict stage, and partial observation.

---

### 93. Byman, Daniel, et al. 2001. [REPORT]

*Trends in Outside Support for Insurgent Movements.* RAND Corporation, MR-1405.

**Pineland use:** External support, sanctuary, organizational sustainability, and foreign sponsorship.

---

### 94. Gompert, David C., Terrence K. Kelly, Brooke Stearns Lawson, Michelle Parker, and Kimberly Colloton. 2009. [REPORT]

*Reconstruction Under Fire: Unifying Civil and Military Counterinsurgency.* RAND Corporation, MG-870.

**Pineland use:** Civil-military interaction, institutional capacity, reconstruction, and integrated governance-security dynamics.

---

### 95. Lawson, Brooke Stearns, et al. 2010. [REPORT]

*Reconstruction Under Fire: Case Studies and Further Analysis of Civil Requirements.* RAND Corporation, MG-870.1.

**Pineland use:** Case-based institutional and civil requirements under insurgency.

---

### 96. Paul, Christopher, et al. 2010. [REPORT]

*Victory Has a Thousand Fathers: Sources of Success in Counterinsurgency.* RAND Corporation, MG-964.

**Pineland use:** Comparative historical COIN practices, support disruption, adaptability, and the danger of reducing outcomes to one dominant mechanism.

---

### 97. Paul, Christopher, Colin P. Clarke, Beth Grill, and Molly Dunigan. 2013. [REPORT]

*Paths to Victory: Lessons from Modern Insurgencies.* RAND Corporation, RR-291/1-OSD.

**Pineland use:** Comparative analysis of 71 post-World War II insurgencies and combinations of correlates associated with outcomes.

---

### 98. Paul, Christopher, Colin P. Clarke, Beth Grill, and Molly Dunigan. 2013. [REPORT]

*Paths to Victory: Detailed Insurgency Case Studies.* RAND Corporation, RR-291/2-OSD.

**Pineland use:** Detailed historical validation cases and comparative mechanism testing.

---

### 99. Johnston, Trevor, Eric E. Mueller, Irina A. Chindea, Heather J. Byrne, Nathan Vest, Colin P. Clarke, Anu Garg, and Howard J. Shatz. 2023. [REPORT]

*Countering Violent Nonstate Actor Financing: Revenue Sources, Financing Strategies, and Tools of Disruption.* RAND Corporation, RRA687-1.

**Pineland use:** Distinct funding channels, organizational budgets, external support, local extraction, resilience, and how financing structure changes organizational incentives.

---

# XIII. Conflict Data and Codebooks Used

### 100. Armed Conflict Location & Event Data Project. [DATA]

*ACLED Codebook*, 2026 version/current project documentation used during design.

**Pineland use:** Event representation, date/location units, actor/event coding, geographic and temporal precision, and synthetic-record design.

---

### 101. Uppsala Conflict Data Program. [DATA]

*UCDP Georeferenced Event Dataset (GED), Version 26.1*, 2026.

**Pineland use:** Historical event validation, village-level geolocation, day-level conflict-event structure, and calibration families.

---

# XIV. Literature Families Invoked but Not Yet Locked to One Canonical Citation

The following ideas have influenced the design, but we have **not yet consistently used one exact paper as the canonical citation**. Do not fabricate a citation. Resolve these during bibliography cleanup.

### A. Radicalization and CVE compartment models

Used conceptually when discussing reproduction-number analogies.

**Status:** Exact canonical paper still to select.

---

### B. Markov State Models and committor analysis

Used for:

\[
P_{ij}(\tau)
\]

committor probabilities,

transition-path ensembles,

mean first-passage times,

and reduced metastable conflict states.

**Status:** Exact mathematical reference still to select.

---

### C. Global Sobol sensitivity analysis

Used conceptually for global parameter sensitivity.

**Status:** Exact canonical sensitivity-analysis source still to select.

---

### D. General uncertainty visualization literature

Used in the proposed analyst interface.

**Status:** Shneiderman is locked for interactive information seeking; exact uncertainty-visualization paper still to select.

---

### E. Semantic zoom / focus-plus-context

Used heavily in the “causal microscope” visualization concept.

**Status:** Exact source was not originally frozen. George W. Furnas’s 1986 “Generalized Fisheye Views” is a strong candidate but should remain marked as a candidate until explicitly adopted into Pineland’s source base.

---

### F. Additional recent ABM calibration literature

Several 2021-2026 calibration/identifiability papers were discussed as a family.

**Status:** Add individually only once actually used for calibration.

---

# XV. Citation Hygiene Rules Going Forward

1. Any paper that changes an equation, state variable, parameter prior, validation target, or architecture decision should be added to this file immediately.

2. Record the exact Pineland mechanism influenced by the source.

3. Distinguish empirical estimates from conceptual inspiration.

4. Never turn a case-specific coefficient into a universal Pineland constant without calibration and sensitivity analysis.

5. Papers surfaced during searches but never actually used should **not** enter the bibliography merely because they looked relevant.

6. RAND reports, historical doctrine, books, datasets, and peer-reviewed research should remain distinguishable by source type.

7. When a parameter is finally calibrated from a source, record:
   - source,
   - sample/case,
   - unit,
   - estimate,
   - uncertainty,
   - transformation into Pineland units,
   - and calibration status.

8. Every future software phase should add a “Research sources added” subsection to its implementation audit.

---

# Current Count

**Peer-reviewed / scholarly articles explicitly used:** approximately 85

**Major books and historical theory works explicitly used:** 4

**RAND reports explicitly used:** 10

**Conflict datasets/codebooks explicitly used:** 2

**Unresolved literature families requiring canonical citations:** 6

This bibliography should be treated as **Version 0.1 of the research-source registry**, not as the final manuscript bibliography.