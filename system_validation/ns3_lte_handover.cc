// Packet-level LTE/EPC A3 handover experiment. Requires ns-3 LTE (tested with 3.46).
#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/lte-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <unordered_set>
#include <vector>

using namespace ns3;

namespace {
std::vector<double> delaysMs;
std::unordered_set<uint32_t> receivedSeqs;
uint32_t duplicatePackets = 0;
uint32_t handoverStarts = 0;
uint32_t handoverEnds = 0;
uint32_t handoverFailures = 0;
double firstHandoverStartMs = -1;
double firstHandoverEndMs = -1;

void ReverseVelocity(Ptr<ConstantVelocityMobilityModel> mobile, double periodS) {
    Vector velocity = mobile->GetVelocity();
    mobile->SetVelocity(Vector(-velocity.x, velocity.y, velocity.z));
    Simulator::Schedule(Seconds(periodS), &ReverseVelocity, mobile, periodS);
}

void OnReceive(Ptr<const Packet> packet, const Address&) {
    Ptr<Packet> copy = packet->Copy();
    SeqTsHeader header;
    if (copy->GetSize() < header.GetSerializedSize()) return;
    copy->RemoveHeader(header);
    if (!receivedSeqs.insert(header.GetSeq()).second) {
        ++duplicatePackets;
        return;
    }
    delaysMs.push_back((Simulator::Now() - header.GetTs()).GetSeconds() * 1000.0);
}

void OnHandoverStart(std::string, uint64_t, uint16_t, uint16_t, uint16_t) {
    ++handoverStarts;
    if (firstHandoverStartMs < 0) firstHandoverStartMs = Simulator::Now().GetSeconds() * 1000.0;
}

void OnHandoverEnd(std::string, uint64_t, uint16_t, uint16_t) {
    ++handoverEnds;
    if (firstHandoverEndMs < 0) firstHandoverEndMs = Simulator::Now().GetSeconds() * 1000.0;
}

void OnHandoverFailure(std::string, uint64_t, uint16_t, uint16_t) {
    ++handoverFailures;
}

double Quantile(const std::vector<double>& sorted, double p) {
    if (sorted.empty()) return -1;
    double index = p * (sorted.size() - 1);
    size_t lower = static_cast<size_t>(index);
    size_t upper = std::min(lower + 1, sorted.size() - 1);
    return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower);
}
} // namespace

int main(int argc, char* argv[]) {
    double hysteresisDb = 3.0;
    uint32_t tttMs = 256;
    double speedMps = 15.0;
    double cellSpacingM = 300.0;
    double startX = -220.0;
    std::string trajectory = "cross";
    double turnPeriodS = 2.0;
    double durationS = 32.0;
    double packetIntervalMs = 10.0;
    double deadlineMs = 20.0;
    uint32_t packetBytes = 200;
    uint32_t run = 1;
    CommandLine cmd(__FILE__);
    cmd.AddValue("hysteresisDb", "A3 hysteresis (dB)", hysteresisDb);
    cmd.AddValue("tttMs", "A3 time-to-trigger (ms)", tttMs);
    cmd.AddValue("speedMps", "UE speed (m/s)", speedMps);
    cmd.AddValue("cellSpacingM", "eNB separation (m)", cellSpacingM);
    cmd.AddValue("startX", "Initial UE x coordinate (m)", startX);
    cmd.AddValue("trajectory", "cross or oscillate", trajectory);
    cmd.AddValue("turnPeriodS", "Velocity reversal period for oscillate (s)", turnPeriodS);
    cmd.AddValue("durationS", "Simulation duration (s)", durationS);
    cmd.AddValue("packetIntervalMs", "UDP inter-packet interval (ms)", packetIntervalMs);
    cmd.AddValue("deadlineMs", "End-to-end packet deadline (ms)", deadlineMs);
    cmd.AddValue("packetBytes", "UDP payload size including 12-byte header", packetBytes);
    cmd.AddValue("run", "ns-3 RNG run", run);
    cmd.Parse(argc, argv);
    if (packetBytes < 12 || packetIntervalMs <= 0 || durationS <= 2 || speedMps <= 0 ||
        (trajectory != "cross" && trajectory != "oscillate") || turnPeriodS <= 0) {
        std::cerr << "Invalid traffic or mobility parameters\n";
        return 2;
    }
    RngSeedManager::SetSeed(47);
    RngSeedManager::SetRun(run);
    Config::SetDefault("ns3::LteHelper::UseIdealRrc", BooleanValue(false));

    Ptr<LteHelper> lte = CreateObject<LteHelper>();
    Ptr<PointToPointEpcHelper> epc = CreateObject<PointToPointEpcHelper>();
    lte->SetEpcHelper(epc);
    lte->SetSchedulerType("ns3::RrFfMacScheduler");
    lte->SetHandoverAlgorithmType("ns3::A3RsrpHandoverAlgorithm");
    lte->SetHandoverAlgorithmAttribute("Hysteresis", DoubleValue(hysteresisDb));
    lte->SetHandoverAlgorithmAttribute("TimeToTrigger", TimeValue(MilliSeconds(tttMs)));

    NodeContainer enbs;
    enbs.Create(2);
    NodeContainer ues;
    ues.Create(1);
    Ptr<ListPositionAllocator> enbPositions = CreateObject<ListPositionAllocator>();
    enbPositions->Add(Vector(-cellSpacingM / 2, 0, 30));
    enbPositions->Add(Vector(cellSpacingM / 2, 0, 30));
    MobilityHelper enbMobility;
    enbMobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    enbMobility.SetPositionAllocator(enbPositions);
    enbMobility.Install(enbs);
    MobilityHelper ueMobility;
    ueMobility.SetMobilityModel("ns3::ConstantVelocityMobilityModel");
    ueMobility.Install(ues);
    Ptr<ConstantVelocityMobilityModel> moving = ues.Get(0)->GetObject<ConstantVelocityMobilityModel>();
    moving->SetPosition(Vector(startX, 0, 1.5));
    moving->SetVelocity(Vector(speedMps, 0, 0));
    if (trajectory == "oscillate") {
        Simulator::Schedule(Seconds(turnPeriodS), &ReverseVelocity, moving, turnPeriodS);
    }

    NetDeviceContainer enbDevices = lte->InstallEnbDevice(enbs);
    NetDeviceContainer ueDevices = lte->InstallUeDevice(ues);
    lte->AddX2Interface(enbs);

    NodeContainer remote;
    remote.Create(1);
    InternetStackHelper internet;
    internet.Install(remote);
    internet.Install(ues);
    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", DataRateValue(DataRate("1Gb/s")));
    p2p.SetDeviceAttribute("Mtu", UintegerValue(1500));
    p2p.SetChannelAttribute("Delay", TimeValue(MilliSeconds(1)));
    NetDeviceContainer backhaul = p2p.Install(epc->GetPgwNode(), remote.Get(0));
    Ipv4AddressHelper address;
    address.SetBase("1.0.0.0", "255.0.0.0");
    address.Assign(backhaul);
    Ipv4StaticRoutingHelper routing;
    routing.GetStaticRouting(remote.Get(0)->GetObject<Ipv4>())
        ->AddNetworkRouteTo(Ipv4Address("7.0.0.0"), Ipv4Mask("255.0.0.0"), 1);
    Ipv4InterfaceContainer ueIps = epc->AssignUeIpv4Address(ueDevices);
    routing.GetStaticRouting(ues.Get(0)->GetObject<Ipv4>())
        ->SetDefaultRoute(epc->GetUeDefaultGatewayAddress(), 1);
    lte->Attach(ueDevices.Get(0), enbDevices.Get(0));

    constexpr uint16_t port = 10000;
    PacketSinkHelper sinkHelper("ns3::UdpSocketFactory", InetSocketAddress(Ipv4Address::GetAny(), port));
    ApplicationContainer sinkApps = sinkHelper.Install(ues.Get(0));
    sinkApps.Start(Seconds(0.2));
    sinkApps.Stop(Seconds(durationS + 0.1));
    Ptr<PacketSink> sink = DynamicCast<PacketSink>(sinkApps.Get(0));
    sink->TraceConnectWithoutContext("Rx", MakeCallback(&OnReceive));
    UdpClientHelper sender(ueIps.GetAddress(0), port);
    sender.SetAttribute("Interval", TimeValue(Seconds(packetIntervalMs / 1000.0)));
    sender.SetAttribute("MaxPackets", UintegerValue(10000000));
    sender.SetAttribute("PacketSize", UintegerValue(packetBytes));
    ApplicationContainer sendApps = sender.Install(remote.Get(0));
    const double trafficStartS = 1.0;
    sendApps.Start(Seconds(trafficStartS));
    sendApps.Stop(Seconds(durationS));

    Config::Connect("/NodeList/*/DeviceList/*/LteUeRrc/HandoverStart", MakeCallback(&OnHandoverStart));
    Config::Connect("/NodeList/*/DeviceList/*/LteUeRrc/HandoverEndOk", MakeCallback(&OnHandoverEnd));
    Config::Connect("/NodeList/*/DeviceList/*/LteEnbRrc/HandoverFailureNoPreamble", MakeCallback(&OnHandoverFailure));
    Config::Connect("/NodeList/*/DeviceList/*/LteEnbRrc/HandoverFailureMaxRach", MakeCallback(&OnHandoverFailure));
    Config::Connect("/NodeList/*/DeviceList/*/LteEnbRrc/HandoverFailureLeaving", MakeCallback(&OnHandoverFailure));
    Config::Connect("/NodeList/*/DeviceList/*/LteEnbRrc/HandoverFailureJoining", MakeCallback(&OnHandoverFailure));

    Simulator::Stop(Seconds(durationS + 0.1));
    Simulator::Run();
    std::sort(delaysMs.begin(), delaysMs.end());
    const uint32_t sent = static_cast<uint32_t>(
        DynamicCast<UdpClient>(sendApps.Get(0))->GetTotalTx() / packetBytes);
    const uint32_t received = static_cast<uint32_t>(delaysMs.size());
    const uint32_t lost = sent >= received ? sent - received : 0;
    const uint32_t late = static_cast<uint32_t>(std::count_if(
        delaysMs.begin(), delaysMs.end(), [deadlineMs](double d) { return d > deadlineMs; }));
    double mean = 0;
    for (double d : delaysMs) mean += d;
    if (received) mean /= received;
    std::cout << std::fixed << std::setprecision(5)
        << "{\"hysteresis_db\":" << hysteresisDb
        << ",\"ttt_ms\":" << tttMs
        << ",\"speed_mps\":" << speedMps
        << ",\"cell_spacing_m\":" << cellSpacingM
        << ",\"start_x_m\":" << startX
        << ",\"trajectory\":\"" << trajectory << "\""
        << ",\"turn_period_s\":" << turnPeriodS
        << ",\"duration_s\":" << durationS
        << ",\"packet_interval_ms\":" << packetIntervalMs
        << ",\"deadline_ms\":" << deadlineMs
        << ",\"packet_bytes\":" << packetBytes
        << ",\"run\":" << run
        << ",\"sent\":" << sent
        << ",\"received\":" << received
        << ",\"lost\":" << lost
        << ",\"duplicate_packets\":" << duplicatePackets
        << ",\"late_received\":" << late
        << ",\"deadline_miss_including_loss\":" << (lost + late)
        << ",\"mean_delay_ms\":" << mean
        << ",\"p95_delay_ms\":" << Quantile(delaysMs, 0.95)
        << ",\"p99_delay_ms\":" << Quantile(delaysMs, 0.99)
        << ",\"handover_starts\":" << handoverStarts
        << ",\"handover_ends\":" << handoverEnds
        << ",\"handover_failures\":" << handoverFailures
        << ",\"first_handover_start_ms\":" << firstHandoverStartMs
        << ",\"first_handover_end_ms\":" << firstHandoverEndMs
        << "}" << std::endl;
    Simulator::Destroy();
    return 0;
}
